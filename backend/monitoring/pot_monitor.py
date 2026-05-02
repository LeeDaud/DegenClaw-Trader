"""AI Pot PnL 监控引擎 — 4 级严重度 + 多因子看涨/看跌信号"""

from __future__ import annotations

import json
import logging
from typing import Any

from config.settings import Settings
from db.database import Database
from signals.signal_state import SignalStateManager, Direction

logger = logging.getLogger(__name__)

_SIGNAL_ICONS = {
    "strong_bullish": "\U0001f7e2\U0001f7e2",  # 🟢🟢
    "bullish": "\U0001f7e2",                    # 🟢
    "neutral": "⚪",                         # ⚪
    "bearish": "\U0001f534",                     # 🔴
    "strong_bearish": "\U0001f534\U0001f534",   # 🔴🔴
}

_TIER_COLORS = {
    "info": "blue",
    "warning": "yellow",
    "important": "orange",
    "critical": "red",
}

_TIER_CALLOUTS = {
    "important": "建议关注该子池风险走势",
    "critical": "⚠️ 紧急：PnL 剧烈波动，请立即关注",
}


class PotPnlMonitor:
    """监控 PotSubAgent 的 PnL 变化，输出按严重度分级的信号告警"""

    def __init__(self, database: Database, state_manager: SignalStateManager | None = None) -> None:
        self.database = database
        self.state_manager = state_manager

    # ----------------------------------------------------------------
    # 公共入口
    # ----------------------------------------------------------------

    def check_sub_pot_changes(
        self,
        round_id: str,
        sub_pots: list[dict[str, Any]],
        settings: Settings,
    ) -> list[dict[str, Any]]:
        """主入口：遍历 sub_pot → 抑制门 → 等级判定 → 信号评分"""
        changes: list[dict[str, Any]] = []
        for sp in sub_pots:
            snapshots = self.database.get_pot_pnl_snapshots(sp["sub_pot_id"], limit=6)
            if len(snapshots) < 2:
                continue

            latest = snapshots[0]
            prev = snapshots[-1]
            starting = float(sp.get("starting_capital", 0) or 0)

            # PnL 变化
            pnl_change = latest["final_pnl"] - prev["final_pnl"]
            pnl_change_pct = self._calc_pnl_change_pct_of_capital(pnl_change, starting)

            # ROI 变化
            latest_roi = ((latest["current_value"] / starting) - 1) * 100 if starting else 0
            prev_roi = ((prev["current_value"] / starting) - 1) * 100 if starting else 0
            roi_change = latest_roi - prev_roi

            # 抑制门 — 低于旧阈值不触发
            if abs(pnl_change_pct) < settings.pot_pnl_change_threshold and abs(roi_change) < settings.pot_roi_change_threshold:
                continue

            direction = self._predict_direction(snapshots, starting)

            # --- 方向确认（通过 StateManager）---
            if self.state_manager is not None:
                # 映射方向分类
                bullbear: Direction | None
                if direction in ("up", "steep_up", "recovery_up"):
                    bullbear = "bullish"
                elif direction in ("down", "steep_down", "pullback_down"):
                    bullbear = "bearish"
                else:
                    bullbear = None
                confirmed, adj_dir, _ = self.state_manager.record_reading(
                    sp["sub_pot_id"], "sub_pot", bullbear, abs(pnl_change_pct),
                )
                if not confirmed:
                    # 方向尚未确认，跳过本轮
                    continue

            tier = self._compute_severity_tier(
                pnl_change_pct, abs(roi_change),
                prev["final_pnl"], latest["final_pnl"],
                starting, snapshots, settings,
            )

            agent_snap = self.database.get_agent_latest_snapshot(str(sp.get("agent_id", "")))
            signal_detail = self._compute_signal_score(sp, snapshots, agent_snap)

            changes.append({
                "sub_pot_id": sp["sub_pot_id"],
                "name": sp["name"],
                "agent_name": sp.get("agent_name", ""),
                "agent_id": str(sp.get("agent_id", "")),
                "token_symbol": sp.get("token_symbol", ""),
                "starting_capital": starting,
                "pnl_before": round(prev["final_pnl"], 2),
                "pnl_now": round(latest["final_pnl"], 2),
                "pnl_change": round(pnl_change, 2),
                "pnl_change_pct_of_capital": round(pnl_change_pct, 2),
                "roi_before": round(prev_roi, 2),
                "roi_now": round(latest_roi, 2),
                "roi_change": round(roi_change, 2),
                "direction": direction,
                "tier": tier,
                "_agent_snapshot": agent_snap,
                **signal_detail,
            })

        return changes

    # ----------------------------------------------------------------
    # 方向预判
    # ----------------------------------------------------------------

    @staticmethod
    def _predict_direction(snapshots: list[dict[str, Any]], capital: float = 0) -> str:
        """增强方向判定：5 点趋势 + 斜坡陡峭分类"""
        pnls = [s["final_pnl"] for s in snapshots[:5]]
        n = len(pnls)
        if n < 2:
            return "stable"

        # 2 点简单比较
        if n == 2:
            diff = pnls[0] - pnls[1]
            if diff > 0:
                slope = abs(diff) / (n - 1)
                return "steep_up" if capital > 0 and slope > 0.5 * capital else "up"
            return "steep_down" if capital > 0 and abs(diff) > 0.5 * capital else "down"

        # 3 点趋势
        d1 = pnls[0] - pnls[1]
        d2 = pnls[1] - pnls[2]
        avg_slope = abs(pnls[0] - pnls[2]) / 2
        is_steep = capital > 0 and avg_slope > 0.5 * capital

        if d1 > 0 and d2 > 0:
            return "steep_up" if is_steep else "up"
        if d1 < 0 and d2 < 0:
            return "steep_down" if is_steep else "down"
        if d1 > 0 and d2 < 0:
            return "pullback_down"
        if d1 < 0 and d2 > 0:
            return "recovery_up"
        return "stable"

    # ----------------------------------------------------------------
    # 严重度等级判定
    # ----------------------------------------------------------------

    @staticmethod
    def _compute_severity_tier(
        pnl_pct: float,
        roi_change_abs: float,
        prev_pnl: float,
        latest_pnl: float,
        capital: float,
        pnl_history: list[dict[str, Any]],
        settings: Settings,
    ) -> str:
        """阈值矩阵 + 自动升级 → 返回等级标签"""
        trigger = max(pnl_pct, roi_change_abs)

        # 正向判定
        if trigger >= settings.pot_pnl_tier_critical_pct:
            tier = "critical"
        elif trigger >= settings.pot_pnl_tier_important_pct:
            tier = "important"
        elif trigger >= settings.pot_pnl_tier_warning_pct:
            tier = "warning"
        elif trigger >= settings.pot_pnl_tier_info_pct:
            tier = "info"
        else:
            return "info"  # 应被抑制门过滤，降级到 info

        # 自动升级
        tier_order = ["info", "warning", "important", "critical"]

        # 符号翻转
        if prev_pnl * latest_pnl < 0:
            idx = max(tier_order.index(tier) + 1, tier_order.index("warning"))
            tier = tier_order[min(idx, len(tier_order) - 1)]

        # 连续同向 3 次
        if len(pnl_history) >= 3:
            pnls = [s["final_pnl"] for s in pnl_history[:3]]
            diffs = [pnls[i] - pnls[i + 1] for i in range(len(pnls) - 1)]
            if all(d > 0 for d in diffs) or all(d < 0 for d in diffs):
                idx = min(tier_order.index(tier) + 1, len(tier_order) - 1)
                tier = tier_order[idx]

        # Capital-relative PnL > 40% 强制 critical
        if capital > 0 and pnl_pct > 40:
            tier = "critical"

        return tier

    # ----------------------------------------------------------------
    # 5 因子信号评分
    # ----------------------------------------------------------------

    @staticmethod
    def _compute_signal_score(
        sp: dict[str, Any],
        snapshots: list[dict[str, Any]],
        agent_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """5 因子聚合评分 → signal_label / raw_score / factors"""
        pnls = [s["final_pnl"] for s in snapshots[:3]]
        latest_pnl = pnls[0] if pnls else 0
        prev_pnl = pnls[-1] if len(pnls) >= 2 else 0
        capital = float(sp.get("starting_capital", 0) or 0)
        realized = float(sp.get("realized_pnl", 0) or 0)
        unrealized = float(sp.get("unrealized_pnl", 0) or 0)
        total = realized + unrealized

        factors: dict[str, int] = {}

        # A: 方向趋势 (weight 2)
        direction = PotPnlMonitor._predict_direction(snapshots, capital)
        a_score = {
            "steep_up": 3, "up": 2, "recovery_up": 1, "stable": 0,
            "pullback_down": -1, "down": -2, "steep_down": -3,
        }.get(direction, 0)
        factors["trend"] = a_score

        # B: PnL 结构 (weight 1)
        if total != 0:
            ratio = abs(realized) / abs(total)
            if realized > 0 and unrealized > 0:
                b_score = 2 if ratio >= 0.6 else 1
            elif realized > 0 and unrealized <= 0:
                b_score = -1
            elif realized <= 0 and unrealized > 0:
                b_score = 1
            else:
                b_score = -2
            # override for extreme ratio
            if total > 0 and ratio >= 0.8:
                b_score = max(b_score, 2)
            elif total < 0 and ratio >= 0.8:
                b_score = min(b_score, -2)
        else:
            b_score = 0
        factors["pnl_structure"] = b_score

        # C: 符号翻转 (weight 3)
        if prev_pnl <= 0 < latest_pnl and latest_pnl - prev_pnl > 0:
            c_score = 4
        elif prev_pnl >= 0 > latest_pnl and latest_pnl - prev_pnl < 0:
            c_score = -4
        else:
            c_score = 0
        factors["sign_change"] = c_score

        # D: 持仓 (weight 1)
        d_score = 0
        try:
            positions = json.loads(sp.get("positions", "[]")) if isinstance(sp.get("positions"), str) else (sp.get("positions") or [])
        except (json.JSONDecodeError, TypeError):
            positions = []
        if positions:
            pos_count = len(positions)
            pos_unrealized = [float(p.get("unrealizedPnl", 0) or 0) for p in positions]
            positive_unrealized = sum(1 for v in pos_unrealized if v > 0)
            negative_large = sum(1 for v in pos_unrealized if v < -100)
            if pos_count >= 6 and positive_unrealized >= pos_count * 0.6:
                d_score = 1
            elif pos_count >= 4:
                d_score = 0
            elif negative_large >= 2:
                d_score = -1
            else:
                d_score = 0
        else:
            d_score = -1
        factors["positions"] = d_score

        # E: Agent 胜率 (weight 1)
        if agent_snapshot:
            wr = float(agent_snapshot.get("win_rate", 0) or 0)
            tc = int(agent_snapshot.get("trade_count", 0) or 0)
            if wr > 60 and tc > 10:
                e_score = 1
            elif wr < 40 and tc > 10:
                e_score = -1
            else:
                e_score = 0
        else:
            e_score = 0
        factors["agent_win_rate"] = e_score

        # 聚合
        raw_score = (a_score * 2) + b_score + (c_score * 3) + d_score + e_score
        signal_label = (
            "strong_bullish" if raw_score >= 5 else
            "bullish" if raw_score >= 2 else
            "bearish" if raw_score <= -2 else
            "strong_bearish" if raw_score <= -5 else
            "neutral"
        )

        return {
            "signal_label": signal_label,
            "raw_score": raw_score,
            "factors": factors,
        }

    # ----------------------------------------------------------------
    # 工具
    # ----------------------------------------------------------------

    @staticmethod
    def _calc_pnl_change_pct_of_capital(pnl_change: float, capital: float) -> float:
        if capital == 0:
            return 0.0
        return (pnl_change / capital) * 100

    # ----------------------------------------------------------------
    # 飞书卡片构建
    # ----------------------------------------------------------------

    @staticmethod
    def build_feishu_card(change: dict[str, Any]) -> dict:
        """为 PnL 变更构建增强飞书消息卡片"""
        tier = change.get("tier", "info")
        signal = change.get("signal_label", "neutral")
        direction = change.get("direction", "stable")
        color = _TIER_COLORS.get(tier, "blue")
        icon = _SIGNAL_ICONS.get(signal, "⚪")
        pnl_pct = change.get("pnl_change_pct_of_capital", 0)
        pnl_str = f"+{pnl_pct}%" if pnl_pct >= 0 else f"{pnl_pct}%"

        # Header
        token_symbol = change.get("token_symbol", "")
        token_line = f"\n{token_symbol}" if token_symbol else ""
        header_text = f"{icon} {signal.upper()} · {tier.upper()} · {change['name']} ({change.get('agent_name', '')}){token_line}"

        elements: list[dict[str, Any]] = [
            # PnL 摘要
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**PnL 变化：** ${change['pnl_before']} → ${change['pnl_now']} "
                        f"（{pnl_str} of capital）\n"
                        f"**ROI 变化：** {change['roi_before']}% → {change['roi_now']}% "
                        f"（{change['roi_change']:+}%）\n"
                        f"**信号强度：** {icon} {signal} | 分数: {change.get('raw_score', 0):+d}"
                    ),
                },
            },
        ]

        # 信号分析（T2+ 展开）
        if tier in ("warning", "important", "critical"):
            factors = change.get("factors", {})
            factor_lines = []
            label_map = {
                "trend": "\U0001f4ca 趋势",
                "pnl_structure": "\U0001f4cb PnL 结构",
                "sign_change": "\U0001f3af 信号",
                "positions": "\U0001f4e6 持仓",
                "agent_win_rate": "\U0001f3c6 Agent",
            }
            for key, label in label_map.items():
                score = factors.get(key, 0)
                sign = "+" if score > 0 else ""
                factor_lines.append(f"{label}：{sign}{score}")
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**信号分析**\n" + "\n".join(factor_lines),
                },
            })

            # Agent 交易信息（如存在）
            agent_snap = change.get("_agent_snapshot")
            if agent_snap and tier in ("important", "critical"):
                wr = float(agent_snap.get("win_rate", 0) or 0)
                tc = int(agent_snap.get("trade_count", 0) or 0)
                r7 = float(agent_snap.get("pnl_7d", 0) or 0)
                elements.append({"tag": "hr"})
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**Agent 状态**\n"
                            f"胜率：{wr:.1f}% | 交易数：{tc}\n"
                            f"7d PnL：${r7:.2f}"
                        ),
                    },
                })

            # Callout（T3+）
            callout = _TIER_CALLOUTS.get(tier)
            if callout:
                elements.append({"tag": "hr"})
                elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{callout}**"}})

        # Footer
        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        elements.append({"tag": "hr"})
        elements.append({"tag": "note", "element": {"tag": "plain_text", "content": f"DegenClaw AI Pot Monitor · {now_str}"}})

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": header_text[:150]},
                "template": color,
            },
            "elements": elements,
        }

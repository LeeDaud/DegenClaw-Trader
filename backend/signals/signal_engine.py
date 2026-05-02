"""预判引擎 — 检测 Agent 大涨/大跌信号"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from db.database import Database
from db.models import Alert, utc_now_iso
from signals.signal_state import SignalStateManager, Direction


SIGNAL_THRESHOLDS = {
    "rank_surge_min": -5,       # 排名提升超过 N 位（rank 值变小 = 排名上升）
    "rank_dump_min": 5,         # 排名下降超过 N 位
    "pnl_surge_min_24h": 8.0,   # 24h PnL 超过此值视为大涨
    "pnl_dump_max_24h": -8.0,   # 24h PnL 低于此值视为大跌
    "volume_spike_ratio": 3.0,  # 成交量增长倍数
    "price_surge_min_1h": 10.0,  # 1h 涨幅
    "price_dump_max_1h": -8.0,  # 1h 跌幅
    "wr_surge_min": 8.0,        # 胜率提升超过 8pp（百分点）
    "wr_dump_max": -8.0,        # 胜率下降超过 8pp
    "combined_surge_score": 35,  # 综合看涨信号分
    "combined_dump_score": 35,  # 综合看跌信号分
}

# 同一 Agent 同一类型预警冷却时间（秒）
ALERT_COOLDOWN_SECONDS = 21600  # 6 小时

# 同一 Agent 全局冷却时间（秒）：任一类型触发后，该 Agent 其他类型也暂不推送
AGENT_GLOBAL_COOLDOWN_SECONDS = 3600  # 1 小时


class SignalEngine:
    def __init__(self, database: Database, state_manager: SignalStateManager | None = None) -> None:
        self.database = database
        self.state_manager = state_manager

    def run_check(self) -> list[Alert]:
        """对所有 Agent 执行一轮信号检测，返回新生成的预警

        聚合策略：同 Agent 的多类型信号合并为一条预警发送，
        避免同一 Agent 同时触发 surge + rank_surge + volume_spike 三条消息。
        """
        now = utc_now_iso()
        alerts: list[Alert] = []

        agents = self.database.list_agents(limit=200)
        for agent in agents:
            agent_id = agent["agent_id"]
            agent_name = agent["name"]

            # 读取最近 3 条快照用于趋势分析
            snapshots = self.database.get_agent_snapshots(agent_id, limit=3)
            if len(snapshots) < 2:
                continue

            latest = snapshots[0]  # 最新
            prev = snapshots[1]    # 上一个

            # 读取市场数据（如果有）
            market = None
            if agent.get("token_address"):
                market = self.database.get_latest_market_snapshot(agent["token_address"])

            # 分析各维度信号
            signals = self._analyze(agent_id, agent_name, latest, prev, market, snapshots)

            # --- 方向确认（通过 StateManager）---
            if self.state_manager is not None and signals:
                # EMA 平滑：对 combined 信号做分数平滑
                for sig in list(signals):
                    if sig["type"] in ("combined_surge", "combined_dump"):
                        smoothed = self.state_manager.get_smoothed_score(agent_id, sig["score"])
                        threshold = SIGNAL_THRESHOLDS.get("combined_surge_score", 35)
                        if smoothed < threshold:
                            signals.remove(sig)

            if not signals:
                continue

            # 方向确认计数
            if self.state_manager is not None:
                direction, raw_score = self._infer_direction(signals)
                confirmed, adj_dir, _ = self.state_manager.record_reading(
                    agent_id, "agent", direction, raw_score,
                )
                if not confirmed:
                    continue

            # --- 聚合策略 ---
            # 同 Agent 的所有信号合并为一条预警，冷却判定以"任一类型最近触发"为准
            # 这样同一 Agent 最多每 GLOBAL_COOLDOWN 发一条，大幅降低频率
            if not self._agent_can_alert(agent_id):
                continue

            alert = self._build_aggregated_alert(agent_id, agent_name, signals, latest, prev, market, now)
            if alert:
                self.database.insert_alert(alert, cooldown_seconds=ALERT_COOLDOWN_SECONDS)
                # 通知 StateManager 方向已推送（后续 can_notify 会据此拦截相反方向）
                if self.state_manager is not None and direction:
                    self.state_manager.mark_notified(agent_id, direction)
                alerts.append(alert)

        return alerts

    def _agent_can_alert(self, agent_id: str) -> bool:
        """检查 Agent 全局冷却：6 小时内是否已推送过任何预警"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        recent = self.database.list_alerts(limit=5, agent_id=agent_id)
        for a in recent:
            try:
                created = datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
                if (now - created).total_seconds() < ALERT_COOLDOWN_SECONDS:
                    return False
            except (ValueError, KeyError):
                continue
        return True

    def _build_aggregated_alert(
        self,
        agent_id: str,
        agent_name: str,
        signals: list[dict[str, Any]],
        latest: dict[str, Any],
        prev: dict[str, Any],
        market: dict[str, Any] | None,
        now: str,
    ) -> Alert | None:
        """将同 Agent 的多个信号合并为一条预警"""
        # 确定最高严重级别
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_sev = max(signals, key=lambda s: severity_order.get(s["severity"], 0))
        total_score = sum(s["score"] for s in signals)

        # 生成汇总标题和详情
        type_labels = {
            "surge": "收益暴涨",
            "dump": "收益暴跌",
            "rank_surge": "排名飙升",
            "rank_dump": "排名暴跌",
            "volume_spike": "成交量异常",
            "price_surge": "价格暴涨",
            "price_dump": "价格暴跌",
            "wr_surge": "胜率飙升",
            "wr_dump": "胜率暴跌",
            "combined_surge": "综合看涨",
            "combined_dump": "综合看跌",
        }

        # 一级策略：按 signals 的方向（看涨/看跌/中性）分成最多两组
        bullish = [s for s in signals if s["type"] in ("surge", "rank_surge", "price_surge", "combined_surge", "wr_surge")]
        bearish = [s for s in signals if s["type"] in ("dump", "rank_dump", "price_dump", "combined_dump", "wr_dump")]
        neutral = [s for s in signals if s["type"] == "volume_spike"]

        parts: list[str] = []
        for group, prefix, emoji in [
            (bullish, "🟢", None),
            (bearish, "🔴", None),
            (neutral, "⚡", None),
        ]:
            for s in group:
                label = type_labels.get(s["type"], s["type"])
                parts.append(f"{label}")

        # 确定整体类型
        if bullish and not bearish:
            agg_type = "combined_surge"
        elif bearish and not bullish:
            agg_type = "combined_dump"
        elif bullish and bearish:
            # 既有看涨又有看跌，以 max_sev 的方向为准
            agg_type = max_sev["type"]
        else:
            agg_type = neutral[0]["type"] if neutral else "surge"

        detail_lines = []
        for s in signals:
            detail_lines.append(f"  • {type_labels.get(s['type'], s['type'])}: {s['detail']}")
        detail = "\n".join(detail_lines)

        alert_id = f"alert_{uuid4().hex[:16]}"
        alert = Alert(
            alert_id=alert_id,
            agent_id=agent_id,
            agent_name=agent_name,
            alert_type=agg_type,
            severity=max_sev["severity"],
            title=f"{agent_name} {len(signals)}项信号触发",
            detail=detail,
            score=total_score,
            snapshot_data=json.dumps({
                "latest_snapshot": {k: str(v) for k, v in latest.items()} if latest else {},
                "prev_snapshot": {k: str(v) for k, v in prev.items()} if prev else {},
                "market": {k: str(v) for k, v in market.items()} if market else {},
            }, ensure_ascii=False),
            notified=False,
            created_at=now,
        )
        return alert

    @staticmethod
    def _infer_direction(signals: list[dict]) -> tuple[Direction | None, float]:
        """从信号列表中推断整体方向

        按看涨/看跌信号的总分比较，高分者获胜。
        Returns:
            (direction, total_score) — direction 为 None 表示中性
        """
        bullish_types = {"surge", "rank_surge", "price_surge", "combined_surge", "wr_surge"}
        bearish_types = {"dump", "rank_dump", "price_dump", "combined_dump", "wr_dump"}

        bull_score = sum(s["score"] for s in signals if s["type"] in bullish_types)
        bear_score = sum(s["score"] for s in signals if s["type"] in bearish_types)

        if bull_score > bear_score and bull_score > 0:
            return ("bullish", bull_score)
        elif bear_score > bull_score and bear_score > 0:
            return ("bearish", bear_score)
        return (None, 0.0)

    def _has_recent_alert(self, agent_id: str, alert_type: str) -> bool:
        """检查冷却期内是否已存在同类预警（保留供兼容，但 run_check 改用 _agent_can_alert）"""
        existing = self.database.list_alerts(
            limit=10, agent_id=agent_id, alert_type=alert_type,
        )
        if not existing:
            return False
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for alert in existing:
            try:
                created = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
                if (now - created).total_seconds() < ALERT_COOLDOWN_SECONDS:
                    return True
            except (ValueError, KeyError):
                continue
        return False

    def _analyze(
        self,
        agent_id: str,
        agent_name: str,
        latest: dict[str, Any],
        prev: dict[str, Any],
        market: dict[str, Any] | None,
        snapshots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        rank_change = (prev.get("rank", 0) or 0) - (latest.get("rank", 0) or 0)
        pnl_24h = float(latest.get("pnl_24h", 0) or 0)
        pnl_7d = float(latest.get("pnl_7d", 0) or 0)
        prev_pnl_7d = float(prev.get("pnl_7d", 0) or 0)
        win_rate = float(latest.get("win_rate", 0) or 0)
        prev_win_rate = float(prev.get("win_rate", 0) or 0)
        drawdown = float(latest.get("max_drawdown", 0) or 0)

        # === 1. 排名飙升 ===
        if rank_change >= SIGNAL_THRESHOLDS["rank_surge_min"] and rank_change < 0:
            signals.append({
                "type": "rank_surge",
                "severity": "high" if abs(rank_change) >= 10 else "medium",
                "title": f"{agent_name} 排名飙升",
                "detail": f"排名从 #{prev['rank']} 上升至 #{latest['rank']}（↑{abs(rank_change)} 位）",
                "score": float(abs(rank_change) * 3),
            })

        # === 2. 排名暴跌 ===
        if rank_change >= SIGNAL_THRESHOLDS["rank_dump_min"] and rank_change > 0:
            signals.append({
                "type": "rank_dump",
                "severity": "critical" if abs(rank_change) >= 10 else "high",
                "title": f"{agent_name} 排名暴跌",
                "detail": f"排名从 #{prev['rank']} 下降至 #{latest['rank']}（↓{rank_change} 位）",
                "score": float(abs(rank_change) * 3),
            })

        # === 3. 收益暴涨 ===
        if pnl_24h >= SIGNAL_THRESHOLDS["pnl_surge_min_24h"]:
            signals.append({
                "type": "surge",
                "severity": "high" if pnl_24h >= 15 else "medium",
                "title": f"{agent_name} 收益暴涨",
                "detail": f"24h PnL +{pnl_24h}%，7d PnL {pnl_7d:+.1f}%，胜率 {win_rate}%",
                "score": pnl_24h * 2,
            })

        # === 4. 收益暴跌 ===
        if pnl_24h <= SIGNAL_THRESHOLDS["pnl_dump_max_24h"]:
            signals.append({
                "type": "dump",
                "severity": "high" if pnl_24h <= -15 else "medium",
                "title": f"{agent_name} 收益暴跌",
                "detail": f"24h PnL {pnl_24h}%，7d PnL {pnl_7d:+.1f}%，最大回撤 {drawdown}%",
                "score": abs(pnl_24h) * 2,
            })

        # === 5. 成交量异常（需要市场数据） ===
        if market:
            vol_24h = float(market.get("volume_24h", 0) or 0)
            vol_1h = float(market.get("volume_1h", 0) or 0)
            price_change_1h = float(market.get("price_change_1h", 0) or 0)
            price_change_24h = float(market.get("price_change_24h", 0) or 0)

            if vol_1h > 0 and vol_24h > 0 and (vol_1h * 24) > vol_24h * SIGNAL_THRESHOLDS["volume_spike_ratio"]:
                signals.append({
                    "type": "volume_spike",
                    "severity": "medium",
                    "title": f"{agent_name} 成交量异常",
                    "detail": f"1h 成交量 ${vol_1h:,.0f}，24h ${vol_24h:,.0f}，短线放量 {((vol_1h * 24) / vol_24h - 1) * 100:.0f}%",
                    "score": min(((vol_1h * 24) / vol_24h) * 5, 30),
                })

            if price_change_1h >= SIGNAL_THRESHOLDS["price_surge_min_1h"]:
                signals.append({
                    "type": "price_surge",
                    "severity": "high" if price_change_1h >= 20 else "medium",
                    "title": f"{agent_name} Token 价格暴涨",
                    "detail": f"1h 涨幅 +{price_change_1h}%，24h 涨幅 {price_change_24h:+.1f}%",
                    "score": price_change_1h * 1.5,
                })

            if price_change_1h <= SIGNAL_THRESHOLDS["price_dump_max_1h"]:
                signals.append({
                    "type": "price_dump",
                    "severity": "high" if price_change_1h <= -15 else "medium",
                    "title": f"{agent_name} Token 价格暴跌",
                    "detail": f"1h 跌幅 {price_change_1h}%，24h 跌幅 {price_change_24h:+.1f}%",
                    "score": abs(price_change_1h) * 1.5,
                })

        # === win_rate 趋势分析（多快照）===
        wr_surge_min = SIGNAL_THRESHOLDS.get("wr_surge_min", 8.0)
        wr_dump_max = SIGNAL_THRESHOLDS.get("wr_dump_max", -8.0)

        # 跨 3 个快照的 win_rate 趋势
        wr_total_change: float = win_rate - prev_win_rate
        wr_trend_detail = f"{prev_win_rate}%→{win_rate}%"
        if len(snapshots) >= 3:
            oldest_wr = float(snapshots[2].get("win_rate", 0) or 0)
            wr_total_change = win_rate - oldest_wr
            wr_trend_detail = f"{oldest_wr}%→{prev_win_rate}%→{win_rate}%"

        # 独立胜率信号（幅度超过阈值时触发）
        if win_rate > 0 and wr_total_change >= wr_surge_min:
            signals.append({
                "type": "wr_surge",
                "severity": "high" if wr_total_change >= 15 else "medium",
                "title": f"{agent_name} 胜率显著提升",
                "detail": f"胜率趋势 {wr_trend_detail}（↑{wr_total_change:.1f}pp）",
                "score": min(wr_total_change * 2, 30),
            })
        elif win_rate > 0 and wr_total_change <= wr_dump_max:
            signals.append({
                "type": "wr_dump",
                "severity": "high" if wr_total_change <= -15 else "medium",
                "title": f"{agent_name} 胜率显著下滑",
                "detail": f"胜率趋势 {wr_trend_detail}（↓{abs(wr_total_change):.1f}pp）",
                "score": min(abs(wr_total_change) * 2, 30),
            })

        # === 6. 综合看涨：win_rate 为主，排名其次 ===
        combined_up = 0
        combined_up_reasons: list[str] = []

        # win_rate 变化（主信号，最高 20 分）
        if wr_total_change > 0:
            wr_pts = min(wr_total_change * 2, 20)
            combined_up += wr_pts
            combined_up_reasons.append(f"胜率↑{wr_total_change:.1f}pp")

        if pnl_7d > prev_pnl_7d:
            combined_up += 5
            combined_up_reasons.append(f"7d PnL 改善 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if rank_change < 0:
            combined_up += abs(rank_change) * 1.5
            combined_up_reasons.append(f"排名↑{abs(rank_change)}")
        if pnl_24h > 5:
            combined_up += 5
            combined_up_reasons.append(f"24h PnL 强劲 (+{pnl_24h}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) > 10:
                combined_up += 3
                combined_up_reasons.append("Token 价格向好")
            if float(market.get("volume_24h", 0) or 0) > 0:
                combined_up += 2

        if combined_up >= SIGNAL_THRESHOLDS["combined_surge_score"]:
            signals.append({
                "type": "combined_surge",
                "severity": "critical" if combined_up >= 40 else "high",
                "title": f"{agent_name} 综合看涨信号",
                "detail": " | ".join(combined_up_reasons),
                "score": combined_up,
            })

        # === 7. 综合看跌：win_rate 为主，排名其次 ===
        combined_down = 0
        combined_down_reasons: list[str] = []

        # win_rate 变化（主信号，最高 20 分）
        if wr_total_change < 0:
            wr_pts = min(abs(wr_total_change) * 2, 20)
            combined_down += wr_pts
            combined_down_reasons.append(f"胜率↓{abs(wr_total_change):.1f}pp")

        if pnl_7d < prev_pnl_7d:
            combined_down += 5
            combined_down_reasons.append(f"7d PnL 恶化 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if rank_change > 0:
            combined_down += rank_change * 1.5
            combined_down_reasons.append(f"排名↓{rank_change}")
        if pnl_24h < -3:
            combined_down += 5
            combined_down_reasons.append(f"24h PnL 为负 ({pnl_24h}%)")
        if drawdown < -10:
            combined_down += 3
            combined_down_reasons.append(f"回撤过大 ({drawdown}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) < -5:
                combined_down += 3
                combined_down_reasons.append("Token 价格走弱")

        if combined_down >= SIGNAL_THRESHOLDS["combined_dump_score"]:
            signals.append({
                "type": "combined_dump",
                "severity": "critical" if combined_down >= 40 else "high",
                "title": f"{agent_name} 综合看跌信号",
                "detail": " | ".join(combined_down_reasons),
                "score": combined_down,
            })

        return signals

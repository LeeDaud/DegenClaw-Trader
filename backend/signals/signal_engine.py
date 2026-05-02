"""预判引擎 — 检测 Agent 大涨/大跌信号

核心改进：
  1. 趋势检测替代单次比较：N 个快照滑动窗口，80%+ 方向一致才确认
  2. PnL 阈值提高：24h PnL ≥15% 或 ≤-12% 才触发
  3. 移除价格预测信号：price_surge/dump 无因果逻辑
  4. 成交量降级为辅助数据，不独立推送
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from db.database import Database
from db.models import Alert, utc_now_iso
from signals.signal_state import SignalStateManager, Direction

SIGNAL_THRESHOLDS = {
    # 排名 — 趋势检测（非单次比较）
    "rank_trend_min_magnitude": 3,      # 趋势中位数变化 ≥ 3 位才有效
    "rank_trend_consistency": 0.8,      # 趋势方向一致比例 ≥ 80%

    # PnL — 阈值提高
    "pnl_surge_min_24h": 15.0,          # 24h PnL ≥ 15% 视为大涨
    "pnl_dump_max_24h": -12.0,          # 24h PnL ≤ -12% 视为大跌

    # 胜率
    "wr_surge_min": 8.0,
    "wr_dump_max": -8.0,

    # 综合信号（保留，由评分引擎 EMA 平滑后决策）
    "combined_surge_score": 35,
    "combined_dump_score": 35,
}

ALERT_COOLDOWN_SECONDS = 21600  # 6 小时


class SignalEngine:
    def __init__(self, database: Database, state_manager: SignalStateManager | None = None,
                 thresholds: dict | None = None, outcome_tracker: Any = None) -> None:
        self.database = database
        self.state_manager = state_manager
        self.outcome_tracker = outcome_tracker
        self.thresholds = {**SIGNAL_THRESHOLDS, **(thresholds or {})}

    # ── 主入口 ─────────────────────────────────────────────────────

    def run_check(self) -> list[Alert]:
        now = utc_now_iso()
        alerts: list[Alert] = []

        agents = self.database.list_agents(limit=200)
        for agent in agents:
            agent_id = agent["agent_id"]
            agent_name = agent["name"]

            # 增加快照数用于趋势检测（6 个 ≈ 5 分钟窗口）
            snapshots = self.database.get_agent_snapshots(agent_id, limit=6)
            if len(snapshots) < 2:
                continue

            latest = snapshots[0]
            prev = snapshots[1]

            market = None
            if agent.get("token_address"):
                market = self.database.get_latest_market_snapshot(agent["token_address"])

            signals = self._analyze(agent_id, agent_name, latest, prev, market, snapshots)

            # --- EMA 平滑（综合信号）---
            if self.state_manager is not None and signals:
                for sig in list(signals):
                    if sig["type"] in ("combined_surge", "combined_dump"):
                        smoothed = self.state_manager.get_smoothed_score(agent_id, sig["score"])
                        threshold = self.thresholds.get("combined_surge_score", 35)
                        if smoothed < threshold:
                            signals.remove(sig)

            if not signals:
                continue

            # --- 方向确认计数 ---
            if self.state_manager is not None:
                direction, raw_score = self._infer_direction(signals)
                confirmed, adj_dir, _ = self.state_manager.record_reading(
                    agent_id, "agent", direction, raw_score,
                )
                if not confirmed:
                    continue

            # --- 全局冷却检查 ---
            if not self._agent_can_alert(agent_id):
                continue

            alert = self._build_aggregated_alert(agent_id, agent_name, signals, latest, prev, market, now)
            if alert:
                self.database.insert_alert(alert, cooldown_seconds=ALERT_COOLDOWN_SECONDS)
                if self.state_manager is not None and direction:
                    self.state_manager.mark_notified(agent_id, direction)
                # 记录 outcome source
                if self.outcome_tracker is not None:
                    params_snapshot = {
                        k: self.thresholds.get(k) for k in (
                            "pnl_surge_min_24h", "pnl_dump_max_24h", "rank_trend_min_magnitude",
                            "combined_surge_score", "combined_dump_score",
                        )
                    }
                    self.outcome_tracker.record_outcome_source(alert, params_snapshot)
                alerts.append(alert)

        return alerts

    # ── 趋势检测（核心改进）─────────────────────────────────────────

    @staticmethod
    def _detect_trend(
        values: list[float],
        consistency_threshold: float = 0.8,
    ) -> tuple[str, float, float]:
        """检测时间序列趋势方向（索引 0 = 最新）

        每对相邻采样计算 diff = older - newer。
        diff > 0：值在改善（排名变小、PnL 增长）
        diff < 0：值在恶化

        Returns:
            (direction, consistency_pct, median_magnitude)
            direction: "up" / "down" / "stable"
        """
        n = len(values)
        if n < 2:
            return ("stable", 0.0, 0.0)

        # 同 run_check 的 rank_change = prev - latest 一致
        diffs = [values[i + 1] - values[i] for i in range(n - 1)]

        total = len(diffs)
        pos = sum(1 for d in diffs if d > 0)   # 改善方向
        neg = sum(1 for d in diffs if d < 0)   # 恶化方向

        if total >= 3 and pos / total >= consistency_threshold:
            up_diffs = [d for d in diffs if d > 0]
            median_mag = sorted(up_diffs)[len(up_diffs) // 2] if up_diffs else 0
            return ("up", pos / total, median_mag)

        if total >= 3 and neg / total >= consistency_threshold:
            down_diffs = [abs(d) for d in diffs if d < 0]
            median_mag = sorted(down_diffs)[len(down_diffs) // 2] if down_diffs else 0
            return ("down", neg / total, median_mag)

        return ("stable", max(pos, neg) / total if total > 0 else 0, 0.0)

    # ── 信号分析 ───────────────────────────────────────────────────

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

        # ── 提取快照时间序列 ──
        rank_values = [float(s.get("rank", 0) or 0) for s in snapshots]
        pnl_7d_values = [float(s.get("pnl_7d", 0) or 0) for s in snapshots]

        pnl_24h = float(latest.get("pnl_24h", 0) or 0)
        pnl_7d = float(latest.get("pnl_7d", 0) or 0)
        prev_pnl_7d = float(prev.get("pnl_7d", 0) or 0)
        win_rate = float(latest.get("win_rate", 0) or 0)
        prev_win_rate = float(prev.get("win_rate", 0) or 0)
        drawdown = float(latest.get("max_drawdown", 0) or 0)

        # ── 排名趋势（替代原来的 2 点比较）──
        rank_dir, rank_cons, rank_mag = self._detect_trend(
            rank_values,
            self.thresholds["rank_trend_consistency"],
        )
        min_rank_mag = self.thresholds["rank_trend_min_magnitude"]

        if rank_dir == "up" and rank_mag >= min_rank_mag:
            signals.append({
                "type": "rank_surge",
                "severity": "high" if rank_mag >= 8 else "medium",
                "title": f"{agent_name} 排名持续飙升",
                "detail": (
                    f"连续 {len(rank_values)-1} 轮排名改善，"
                    f"中位数变化 {rank_mag:.0f} 位/轮，"
                    f"一致率 {rank_cons:.0%}"
                ),
                "score": rank_mag * 3,
            })

        elif rank_dir == "down" and rank_mag >= min_rank_mag:
            signals.append({
                "type": "rank_dump",
                "severity": "critical" if rank_mag >= 8 else "high",
                "title": f"{agent_name} 排名持续暴跌",
                "detail": (
                    f"连续 {len(rank_values)-1} 轮排名恶化，"
                    f"中位数变化 {rank_mag:.0f} 位/轮，"
                    f"一致率 {rank_cons:.0%}"
                ),
                "score": rank_mag * 3,
            })

        # ── PnL 暴涨/暴跌 ──
        # 24h PnL 绝对值检测（趋势检测作为辅助确认）
        if pnl_24h >= self.thresholds["pnl_surge_min_24h"]:
            # pnl_7d 趋势确认：取反解决 _detect_trend 设计为 rank（越小越好）的符号问题
            pnl_dir, _, _ = self._detect_trend([-v for v in pnl_7d_values])
            if pnl_dir in ("up", "stable"):
                signals.append({
                    "type": "surge",
                    "severity": "high" if pnl_24h >= 25 else "medium",
                    "title": f"{agent_name} 收益暴涨",
                    "detail": f"24h PnL +{pnl_24h}%，7d PnL {pnl_7d:+.1f}%，胜率 {win_rate}%",
                    "score": pnl_24h * 2,
                })

        if pnl_24h <= self.thresholds["pnl_dump_max_24h"]:
            pnl_dir, _, _ = self._detect_trend([-v for v in pnl_7d_values])
            if pnl_dir in ("down", "stable"):
                signals.append({
                    "type": "dump",
                    "severity": "high" if pnl_24h <= -25 else "medium",
                    "title": f"{agent_name} 收益暴跌",
                    "detail": f"24h PnL {pnl_24h}%，7d PnL {pnl_7d:+.1f}%，最大回撤 {drawdown}%",
                    "score": abs(pnl_24h) * 2,
                })

        # ── 价格数据 → 仅保留在 snapshot_data 中，不推送信号 ──
        # 价格用作"预期兑现参考"（在聚合预警的 snapshot_data 中查看）
        # 不再生成 price_surge / price_dump

        # ── 成交量 → 不独立推送，仅用于综合信号 ──
        # volume_spike 不再作为独立信号

        # ── win_rate 趋势分析 ──
        wr_surge_min = self.thresholds.get("wr_surge_min", 8.0)
        wr_dump_max = self.thresholds.get("wr_dump_max", -8.0)

        wr_total_change: float = win_rate - prev_win_rate
        wr_trend_detail = f"{prev_win_rate}%→{win_rate}%"
        if len(snapshots) >= 3:
            oldest_wr = float(snapshots[2].get("win_rate", 0) or 0)
            wr_total_change = win_rate - oldest_wr
            wr_trend_detail = f"{oldest_wr}%→{prev_win_rate}%→{win_rate}%"

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

        # ── 综合看涨 ──
        combined_up = 0
        combined_up_reasons: list[str] = []

        if wr_total_change > 0:
            wr_pts = min(wr_total_change * 2, 20)
            combined_up += wr_pts
            combined_up_reasons.append(f"胜率↑{wr_total_change:.1f}pp")

        if pnl_7d > prev_pnl_7d:
            combined_up += 5
            combined_up_reasons.append(f"7d PnL 改善 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if rank_dir == "up":
            combined_up += rank_mag * 1.5
            combined_up_reasons.append(f"排名趋势↑({rank_mag:.0f}/轮)")
        if pnl_24h > 10:
            combined_up += 5
            combined_up_reasons.append(f"24h PnL 强劲 (+{pnl_24h}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) > 10:
                combined_up += 3
                combined_up_reasons.append("Token 价格向好")

        if combined_up >= self.thresholds["combined_surge_score"]:
            signals.append({
                "type": "combined_surge",
                "severity": "critical" if combined_up >= 40 else "high",
                "title": f"{agent_name} 综合看涨信号",
                "detail": " | ".join(combined_up_reasons),
                "score": combined_up,
            })

        # ── 综合看跌 ──
        combined_down = 0
        combined_down_reasons: list[str] = []

        if wr_total_change < 0:
            wr_pts = min(abs(wr_total_change) * 2, 20)
            combined_down += wr_pts
            combined_down_reasons.append(f"胜率↓{abs(wr_total_change):.1f}pp")

        if pnl_7d < prev_pnl_7d:
            combined_down += 5
            combined_down_reasons.append(f"7d PnL 恶化 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if rank_dir == "down":
            combined_down += rank_mag * 1.5
            combined_down_reasons.append(f"排名趋势↓({rank_mag:.0f}/轮)")
        if pnl_24h < -5:
            combined_down += 5
            combined_down_reasons.append(f"24h PnL 为负 ({pnl_24h}%)")
        if drawdown < -10:
            combined_down += 3
            combined_down_reasons.append(f"回撤过大 ({drawdown}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) < -5:
                combined_down += 3
                combined_down_reasons.append("Token 价格走弱")

        if combined_down >= self.thresholds["combined_dump_score"]:
            signals.append({
                "type": "combined_dump",
                "severity": "critical" if combined_down >= 40 else "high",
                "title": f"{agent_name} 综合看跌信号",
                "detail": " | ".join(combined_down_reasons),
                "score": combined_down,
            })

        return signals

    # ── 辅助方法 ───────────────────────────────────────────────────

    def _agent_can_alert(self, agent_id: str) -> bool:
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
        severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        max_sev = max(signals, key=lambda s: severity_order.get(s["severity"], 0))
        total_score = sum(s["score"] for s in signals)

        type_labels = {
            "surge": "收益暴涨",
            "dump": "收益暴跌",
            "rank_surge": "排名趋势飙升",
            "rank_dump": "排名趋势暴跌",
            "wr_surge": "胜率飙升",
            "wr_dump": "胜率暴跌",
            "combined_surge": "综合看涨",
            "combined_dump": "综合看跌",
        }

        bullish = [s for s in signals if s["type"] in ("surge", "rank_surge", "combined_surge", "wr_surge")]
        bearish = [s for s in signals if s["type"] in ("dump", "rank_dump", "combined_dump", "wr_dump")]

        if bullish and not bearish:
            agg_type = "combined_surge"
        elif bearish and not bullish:
            agg_type = "combined_dump"
        elif bullish and bearish:
            agg_type = max_sev["type"]
        else:
            agg_type = "surge"

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

        按看涨/看跌信号的总分比较。
        """
        bullish_types = {"surge", "rank_surge", "combined_surge", "wr_surge"}
        bearish_types = {"dump", "rank_dump", "combined_dump", "wr_dump"}

        bull_score = sum(s["score"] for s in signals if s["type"] in bullish_types)
        bear_score = sum(s["score"] for s in signals if s["type"] in bearish_types)

        if bull_score > bear_score and bull_score > 0:
            return ("bullish", bull_score)
        elif bear_score > bull_score and bear_score > 0:
            return ("bearish", bear_score)
        return (None, 0.0)

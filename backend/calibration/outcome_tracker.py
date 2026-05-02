"""预测结果追踪 + 精度反馈 — 记录 → 回检 → 统计 → 自动调参"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from db.database import Database
from db.models import Alert, SignalOutcome, utc_now_iso
from signals.signal_state import SignalStateManager

logger = logging.getLogger(__name__)

# 观察窗口（秒）— 按信号类型
_OUTCOME_WINDOWS: dict[str, int] = {
    "surge": 1800,
    "dump": 1800,
    "rank_surge": 1800,
    "rank_dump": 1800,
    "combined_surge": 3600,
    "combined_dump": 3600,
    "wr_surge": 7200,
    "wr_dump": 7200,
}

# 看涨信号 → 判定时检查指标是否改善
_BULLISH_TYPES = {"surge", "rank_surge", "combined_surge", "wr_surge"}
_BEARISH_TYPES = {"dump", "rank_dump", "combined_dump", "wr_dump"}

# 精度反馈边界
_TUNE_LOWER_BOUND = 40  # 低于此→收紧
_TUNE_UPPER_BOUND = 75  # 高于此→放松


class OutcomeTracker:
    """预测结果追踪 + 精度反馈

    三大职责：
    1. record_outcome_source() — 预警生成时记录
    2. check_outcomes() — 定期回检待评估预警
    3. auto_tune() — 根据命中率自动调参
    """

    def __init__(self, database: Database, state_manager: SignalStateManager | None = None) -> None:
        self.db = database
        self.state_manager = state_manager

    # ── 记录预警 ─────────────────────────────────────────────────

    def record_outcome_source(self, alert: Alert, params_snapshot: dict | None = None) -> None:
        """预警推送时写入 signal_outcomes，供后续回检"""
        # signal_type → direction 映射
        direction = "bullish" if alert.alert_type in _BULLISH_TYPES else "bearish"

        outcome = SignalOutcome(
            alert_id=alert.alert_id,
            agent_id=alert.agent_id,
            signal_type=alert.alert_type,
            direction=direction,
            score=alert.score,
            params_snapshot=json.dumps(params_snapshot or {}, ensure_ascii=False),
            predicted_at=alert.created_at,
        )
        self.db.insert_signal_outcome(outcome)
        logger.debug("已记录 outcome source: %s %s", alert.alert_id, alert.alert_type)

    # ── 结果回检 ─────────────────────────────────────────────────

    def check_outcomes(self) -> dict[str, int]:
        """遍历所有待回检的预警，判定预测是否正确"""
        outcomes = self.db.get_pending_outcomes(limit=50)
        stats: dict[str, int] = {"checked": 0, "correct": 0, "wrong": 0, "skipped": 0}

        for o in outcomes:
            result = self._evaluate_outcome(o)
            if result is None:
                continue  # 观察窗口未到，跳过

            self.db.update_outcome(
                o["id"], result["outcome"],
                json.dumps(result["detail"], ensure_ascii=False),
                utc_now_iso(),
            )
            stats["checked"] += 1
            outcome_code = result["outcome"]
            if outcome_code == 1:
                stats["correct"] += 1
            elif outcome_code == 0:
                stats["wrong"] += 1
            else:
                stats["skipped"] += 1

        if stats["checked"] > 0:
            logger.info("Outcome check: checked=%d correct=%d wrong=%d skipped=%d",
                        stats["checked"], stats["correct"], stats["wrong"], stats["skipped"])

        return stats

    def _evaluate_outcome(self, outcome: dict) -> dict | None:
        """判定单个预警的正确性

        Returns:
            {"outcome": 1|0|-1, "detail": {...}} — None 表示暂不可判断
        """
        signal_type = outcome["signal_type"]
        direction = outcome["direction"]
        predicted_at = outcome["predicted_at"]
        agent_id = outcome["agent_id"]

        window_seconds = _OUTCOME_WINDOWS.get(signal_type, 1800)
        predicted_dt = datetime.fromisoformat(predicted_at.replace("Z", "+00:00"))

        # 观察窗口结束时间
        eval_cutoff = predicted_dt + timedelta(seconds=window_seconds)
        now = datetime.now(timezone.utc)
        if now < eval_cutoff:
            return None  # 窗口未到，下次再检

        eval_iso = eval_cutoff.isoformat().replace("+00:00", "Z")

        # 获取预警时和观察窗口后的快照
        before = self.db.get_agent_snapshot_before(agent_id, predicted_at)
        after = self.db.get_agent_snapshot_before(agent_id, eval_iso)

        if not before or not after:
            return {"outcome": -1, "detail": {"reason": "insufficient_snapshots"}}

        return self._judge(signal_type, direction, before, after)

    @staticmethod
    def _judge(
        signal_type: str,
        direction: str,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict:
        """按信号类型判定预测是否正确

        看涨成功条件：rank 改善 或 PnL 增长 或 胜率提升
        看跌成功条件：rank 恶化 或 PnL 下跌 或 胜率下滑

        Returns:
            {"outcome": 1|0|-1, "detail": {...}}
        """
        rank_before = int(before.get("rank", 0) or 0)
        rank_after = int(after.get("rank", 0) or 0)
        pnl_before = float(before.get("pnl_24h", 0) or 0)
        pnl_after = float(after.get("pnl_24h", 0) or 0)
        wr_before = float(before.get("win_rate", 0) or 0)
        wr_after = float(after.get("win_rate", 0) or 0)

        rank_change = rank_before - rank_after  # positive = improvement
        pnl_change = pnl_after - pnl_before
        wr_change = wr_after - wr_before

        detail = {
            "rank": {"before": rank_before, "after": rank_after, "change": rank_change},
            "pnl_24h": {"before": pnl_before, "after": pnl_after, "change": pnl_change},
            "win_rate": {"before": round(wr_before, 1), "after": round(wr_after, 1), "change": round(wr_change, 1)},
        }

        if direction == "bullish":
            # 看涨：任一因子改善即算正确
            score = 0
            if rank_change >= 2:
                score += 1
            if pnl_change >= 5:
                score += 1
            if signal_type in ("wr_surge", "combined_surge") and wr_change >= 3:
                score += 1
            outcome = 1 if score >= 1 else 0
            detail["reason"] = "rank_improved" if rank_change >= 2 else "pnl_grew" if pnl_change >= 5 else "no_improvement"
        elif direction == "bearish":
            score = 0
            if rank_change <= -2:
                score += 1
            if pnl_change <= -5:
                score += 1
            if signal_type in ("wr_dump", "combined_dump") and wr_change <= -3:
                score += 1
            outcome = 1 if score >= 1 else 0
            detail["reason"] = "rank_worsened" if rank_change <= -2 else "pnl_dropped" if pnl_change <= -5 else "no_worsening"
        else:
            outcome = -1
            detail["reason"] = "unknown_direction"

        return {"outcome": outcome, "detail": detail}

    # ── 命中率统计 ─────────────────────────────────────────────

    def get_signal_type_hit_rates(self, since_hours: int = 24) -> dict[str, dict]:
        """返回各信号类型的命中率"""
        signal_types = [
            "surge", "dump", "rank_surge", "rank_dump",
            "combined_surge", "combined_dump", "wr_surge", "wr_dump",
        ]
        since = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat().replace("+00:00", "Z")

        results: dict[str, dict] = {}
        for st in signal_types:
            hit = self.db.get_hit_rate(st, since)
            if hit is not None:
                results[st] = {"hit_rate": hit}

        return results

    # ── 自动调参 ───────────────────────────────────────────────

    def auto_tune(self) -> dict[str, Any]:
        """根据命中率自动调整信号参数"""
        config = self.db.get_all_config()
        hit_rates = self.get_signal_type_hit_rates(since_hours=24)
        lower = float(config.get("hit_rate_lower_bound", str(_TUNE_LOWER_BOUND)))
        upper = float(config.get("hit_rate_upper_bound", str(_TUNE_UPPER_BOUND)))

        adjustments: dict[str, str] = {}

        # surge → pnl_surge_min_24h
        if "surge" in hit_rates:
            hr = hit_rates["surge"]["hit_rate"]
            current = float(config.get("pnl_surge_min_24h", "15"))
            if hr < lower:
                new_val = min(current * 1.15, 30.0)
                adjustments["pnl_surge_min_24h"] = f"{new_val:.1f}"
            elif hr > upper:
                new_val = max(current * 0.9, 10.0)
                adjustments["pnl_surge_min_24h"] = f"{new_val:.1f}"

        # dump → pnl_dump_max_24h（注意是负数，收紧=更负）
        if "dump" in hit_rates:
            hr = hit_rates["dump"]["hit_rate"]
            current = float(config.get("pnl_dump_max_24h", "-12"))
            if hr < lower:
                new_val = max(current * 1.15, -25.0)  # 更严格（-12 → -13.8）
                adjustments["pnl_dump_max_24h"] = f"{new_val:.1f}"
            elif hr > upper:
                new_val = min(current * 0.9, -8.0)   # 更宽松（-12 → -10.8）
                adjustments["pnl_dump_max_24h"] = f"{new_val:.1f}"

        # rank_surge / rank_dump → rank_trend_min_magnitude
        rank_keys = ("rank_surge", "rank_dump")
        rank_hit = [hit_rates[k]["hit_rate"] for k in rank_keys if k in hit_rates]

        if "rank_surge" in hit_rates or "rank_dump" in hit_rates:
            current_rank_mag = float(config.get("rank_trend_min_magnitude", "3"))
            rank_avg_hr = sum(rank_hit) / len(rank_hit) if rank_hit else 50.0
            if rank_avg_hr < lower:
                new_val = min(int(current_rank_mag) + 1, 8)
                adjustments["rank_trend_min_magnitude"] = str(new_val)
            elif rank_avg_hr > upper:
                new_val = max(int(current_rank_mag) - 1, 2)
                adjustments["rank_trend_min_magnitude"] = str(new_val)

        # wr_surge / wr_dump → wr_surge_min / wr_dump_max
        if "wr_surge" in hit_rates:
            hr = hit_rates["wr_surge"]["hit_rate"]
            current_wr = float(config.get("wr_surge_min", "8"))
            if hr < lower:
                adjustments["wr_surge_min"] = f"{min(current_wr * 1.15, 15.0):.1f}"
            elif hr > upper:
                adjustments["wr_surge_min"] = f"{max(current_wr * 0.9, 5.0):.1f}"

        if "wr_dump" in hit_rates:
            hr = hit_rates["wr_dump"]["hit_rate"]
            current_wr = float(config.get("wr_dump_max", "-8"))
            if hr < lower:
                adjustments["wr_dump_max"] = f"{max(current_wr * 1.15, -15.0):.1f}"
            elif hr > upper:
                adjustments["wr_dump_max"] = f"{min(current_wr * 0.9, -5.0):.1f}"

        # combined_surge / combined_dump → combined_*_score
        combined_up_hit = hit_rates.get("combined_surge", {}).get("hit_rate")
        combined_down_hit = hit_rates.get("combined_dump", {}).get("hit_rate")

        if combined_up_hit is not None:
            current_cu = float(config.get("combined_surge_score", "35"))
            if combined_up_hit < lower:
                adjustments["combined_surge_score"] = f"{min(int(current_cu) + 5, 50)}"
            elif combined_up_hit > upper:
                adjustments["combined_surge_score"] = f"{max(int(current_cu) - 5, 25)}"

        if combined_down_hit is not None:
            current_cd = float(config.get("combined_dump_score", "35"))
            if combined_down_hit < lower:
                adjustments["combined_dump_score"] = f"{min(int(current_cd) + 5, 50)}"
            elif combined_down_hit > upper:
                adjustments["combined_dump_score"] = f"{max(int(current_cd) - 5, 25)}"

        # 持久化调整
        for key, value in adjustments.items():
            self.db.set_config(key, value)

        # 同步到 state_manager 的运行时配置
        if self.state_manager is not None:
            if "confirmation_count" in adjustments:
                self.state_manager.update_config("confirmation_count", int(adjustments["confirmation_count"]))
            if "direction_cooldown" in adjustments:
                self.state_manager.update_config("direction_cooldown", int(adjustments["direction_cooldown"]))

        if adjustments:
            logger.info("自动调参: 已调整 %s", list(adjustments.keys()))

        return {"adjusted_keys": list(adjustments.keys()), "new_config": adjustments}

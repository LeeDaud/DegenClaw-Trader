"""历史回测引擎 — 用历史快照模拟信号检测，评估参数效果"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from db.database import Database
from signals.signal_engine import SIGNAL_THRESHOLDS, SignalEngine
from signals.signal_state import SignalStateManager

logger = logging.getLogger(__name__)

# 观察窗口（秒），判断信号是否正确的等待时间
_OBSERVATION_WINDOW = 1800  # 30 分钟


@dataclass
class BacktestSignal:
    """回测中生成的一条信号"""
    agent_id: str
    signal_type: str
    triggered_at: str
    direction: str
    score: float
    params_used: dict
    outcome: int | None = None   # 1=正确, 0=错误, -1=数据不足
    outcome_detail: str = ""


@dataclass
class BacktestResult:
    """一次回测的结果统计"""
    params: dict
    total_signals: int = 0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    by_type: dict[str, dict] = field(default_factory=dict)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1_score(self) -> float:
        p = self.precision
        r = self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


class BacktestEngine:
    """用历史数据回测信号引擎

    按时间窗口滑动，在每个窗口运行信号检测，
    然后跨过观察窗口判定信号是否正确。
    """

    def __init__(self, database: Database) -> None:
        self.db = database

    def run(
        self,
        params: dict,
        start_time: str | None = None,
        end_time: str | None = None,
        agent_ids: list[str] | None = None,
    ) -> BacktestResult:
        """运行一次回测

        Args:
            params: 覆盖 SIGNAL_THRESHOLDS 的参数
            start_time: 回测起始时间（None=7 天前）
            end_time: 回测结束时间（None=现在）
            agent_ids: 指定 Agent（None=全部有快照的 Agent）
        """
        now = datetime.now(timezone.utc)
        if end_time is None:
            end_time = now.isoformat().replace("+00:00", "Z")
        if start_time is None:
            start_time = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")

        if agent_ids is None:
            agents = self.db.list_agents(limit=200)
            agent_ids = [a["agent_id"] for a in agents]

        result = BacktestResult(params=params)
        signals_by_agent: dict[str, list[BacktestSignal]] = defaultdict(list)

        for aid in agent_ids:
            signals = self._backtest_agent(aid, params, start_time, end_time)
            for sig in signals:
                signals_by_agent[aid].append(sig)

        # 判定信号结果
        for aid, sig_list in signals_by_agent.items():
            for sig in sig_list:
                outcome = self._evaluate_signal(aid, sig, end_time)
                sig.outcome = outcome
                if outcome == 1:
                    result.true_positives += 1
                elif outcome == 0:
                    result.false_positives += 1

                # 按类型统计
                if sig.signal_type not in result.by_type:
                    result.by_type[sig.signal_type] = {"tp": 0, "fp": 0, "fn": 0, "total": 0}
                result.by_type[sig.signal_type]["total"] += 1
                if outcome == 1:
                    result.by_type[sig.signal_type]["tp"] += 1
                elif outcome == 0:
                    result.by_type[sig.signal_type]["fp"] += 1

            result.total_signals += len(sig_list)

        # 漏报检测
        false_negatives = self._detect_false_negatives(agent_ids, params, start_time, end_time, signals_by_agent)
        result.false_negatives = len(false_negatives)

        return result

    def _backtest_agent(
        self,
        agent_id: str,
        params: dict,
        start_time: str,
        end_time: str,
    ) -> list[BacktestSignal]:
        """对单个 Agent 运行区间回测"""
        snapshots = self.db.get_agent_snapshots(agent_id, limit=200)
        # 过滤时间范围
        snapshots = [s for s in snapshots if start_time <= s.get("snapshot_at", "") <= end_time]
        if len(snapshots) < 6:
            return []

        signals: list[BacktestSignal] = []

        # 用 5 个快照的滑动窗口检测信号（模拟 SignalEngine._analyze）
        for i in range(len(snapshots) - 5):
            window = snapshots[i:i + 6]
            sigs = self._simulate_analyze(agent_id, window, params)
            signals.extend(sigs)

        return signals

    def _simulate_analyze(
        self,
        agent_id: str,
        snapshots: list[dict],
        params: dict,
    ) -> list[BacktestSignal]:
        """模拟 SignalEngine._analyze 的逻辑"""
        from signals.signal_engine import SignalEngine

        threshold = {**SIGNAL_THRESHOLDS, **params}
        engine = SignalEngine(self.db, thresholds=threshold)

        latest = snapshots[0]
        prev = snapshots[1]
        rank_values = [float(s.get("rank", 0) or 0) for s in snapshots]
        pnl_7d_values = [float(s.get("pnl_7d", 0) or 0) for s in snapshots]
        pnl_24h = float(latest.get("pnl_24h", 0) or 0)
        pnl_7d = float(latest.get("pnl_7d", 0) or 0)
        prev_pnl_7d = float(prev.get("pnl_7d", 0) or 0)
        win_rate = float(latest.get("win_rate", 0) or 0)
        prev_win_rate = float(prev.get("win_rate", 0) or 0)
        drawdown = float(latest.get("max_drawdown", 0) or 0)

        detected: list[BacktestSignal] = []

        # 排名趋势
        rank_dir, rank_cons, rank_mag = engine._detect_trend(rank_values)
        min_rank_mag = threshold["rank_trend_min_magnitude"]
        if rank_dir == "up" and rank_mag >= min_rank_mag:
            detected.append(BacktestSignal(
                agent_id=agent_id, signal_type="rank_surge", direction="bullish",
                triggered_at=str(snapshots[0].get("snapshot_at", "")),
                score=rank_mag * 3, params_used=threshold,
            ))
        elif rank_dir == "down" and rank_mag >= min_rank_mag:
            detected.append(BacktestSignal(
                agent_id=agent_id, signal_type="rank_dump", direction="bearish",
                triggered_at=str(snapshots[0].get("snapshot_at", "")),
                score=rank_mag * 3, params_used=threshold,
            ))

        # PnL
        if pnl_24h >= threshold["pnl_surge_min_24h"]:
            pnl_dir, _, _ = engine._detect_trend([-v for v in pnl_7d_values])
            if pnl_dir in ("up", "stable"):
                detected.append(BacktestSignal(
                    agent_id=agent_id, signal_type="surge", direction="bullish",
                    triggered_at=str(snapshots[0].get("snapshot_at", "")),
                    score=pnl_24h * 2, params_used=threshold,
                ))

        if pnl_24h <= threshold["pnl_dump_max_24h"]:
            pnl_dir, _, _ = engine._detect_trend([-v for v in pnl_7d_values])
            if pnl_dir in ("down", "stable"):
                detected.append(BacktestSignal(
                    agent_id=agent_id, signal_type="dump", direction="bearish",
                    triggered_at=str(snapshots[0].get("snapshot_at", "")),
                    score=abs(pnl_24h) * 2, params_used=threshold,
                ))

        # 胜率
        wr_surge_min = threshold.get("wr_surge_min", 8.0)
        wr_dump_max = threshold.get("wr_dump_max", -8.0)
        wr_change = win_rate - prev_win_rate
        if win_rate > 0 and wr_change >= wr_surge_min:
            detected.append(BacktestSignal(
                agent_id=agent_id, signal_type="wr_surge", direction="bullish",
                triggered_at=str(snapshots[0].get("snapshot_at", "")),
                score=min(wr_change * 2, 30), params_used=threshold,
            ))
        elif win_rate > 0 and wr_change <= wr_dump_max:
            detected.append(BacktestSignal(
                agent_id=agent_id, signal_type="wr_dump", direction="bearish",
                triggered_at=str(snapshots[0].get("snapshot_at", "")),
                score=min(abs(wr_change) * 2, 30), params_used=threshold,
            ))

        return detected

    def _evaluate_signal(self, agent_id: str, signal: BacktestSignal, until: str) -> int:
        """判定信号是否正确（1=正确, 0=错误, -1=数据不足）"""
        from datetime import datetime, timezone

        triggered_at = signal.triggered_at
        try:
            t_dt = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))
            eval_dt = t_dt + timedelta(seconds=_OBSERVATION_WINDOW)
            eval_iso = eval_dt.isoformat().replace("+00:00", "Z")
        except (ValueError, TypeError):
            return -1

        # 检查该 Agent 在观察窗口后的最新快照
        after = self.db.get_agent_snapshot_before(agent_id, eval_iso)
        if not after:
            return -1

        # 获取信号时刻的快照
        before = self.db.get_agent_snapshot_before(agent_id, triggered_at)
        if not before:
            return -1

        return self._judge_signal(signal.signal_type, signal.direction, before, after)

    @staticmethod
    def _judge_signal(signal_type: str, direction: str, before: dict, after: dict) -> int:
        """判定单个信号的正确性（同 OutcomeTracker._judge 逻辑）"""
        rank_before = int(before.get("rank", 0) or 0)
        rank_after = int(after.get("rank", 0) or 0)
        pnl_before = float(before.get("pnl_24h", 0) or 0)
        pnl_after = float(after.get("pnl_24h", 0) or 0)

        rank_change = rank_before - rank_after
        pnl_change = pnl_after - pnl_before

        if direction == "bullish":
            score = 0
            if rank_change >= 2:
                score += 1
            if pnl_change >= 5:
                score += 1
            return 1 if score >= 1 else 0
        elif direction == "bearish":
            score = 0
            if rank_change <= -2:
                score += 1
            if pnl_change <= -5:
                score += 1
            return 1 if score >= 1 else 0
        return -1

    def _detect_false_negatives(
        self,
        agent_ids: list[str],
        params: dict,
        start_time: str,
        end_time: str,
        triggered: dict[str, list[BacktestSignal]],
    ) -> list[BacktestSignal]:
        """检测漏报：应该触发但实际未触发的信号"""
        fn_list: list[BacktestSignal] = []
        threshold = {**SIGNAL_THRESHOLDS, **params}
        min_pnl_surge = threshold.get("pnl_surge_min_24h", 15.0)
        max_pnl_dump = threshold.get("pnl_dump_max_24h", -12.0)

        for aid in agent_ids:
            snapshots = self.db.get_agent_snapshots(aid, limit=100)
            snapshots = [s for s in snapshots if start_time <= s.get("snapshot_at", "") <= end_time]
            if len(snapshots) < 6:
                continue

            triggered_set = set()
            for sig in triggered.get(aid, []):
                triggered_set.add((sig.signal_type, sig.triggered_at[:16]))  # 分钟级精度

            for i in range(5, len(snapshots)):
                window = snapshots[i - 5:i + 1]
                latest = window[-1]
                ts = str(latest.get("snapshot_at", ""))

                pnl_24h = float(latest.get("pnl_24h", 0) or 0)
                win_rate = float(latest.get("win_rate", 0) or 0)

                # 检查 PnL 大幅跳变但未触发
                if pnl_24h >= min_pnl_surge + 5 and ("surge", ts[:16]) not in triggered_set:
                    fn_list.append(BacktestSignal(
                        agent_id=aid, signal_type="surge", direction="bullish",
                        triggered_at=ts, score=pnl_24h * 2, params_used=threshold,
                    ))
                if pnl_24h <= max_pnl_dump - 5 and ("dump", ts[:16]) not in triggered_set:
                    fn_list.append(BacktestSignal(
                        agent_id=aid, signal_type="dump", direction="bearish",
                        triggered_at=ts, score=abs(pnl_24h) * 2, params_used=threshold,
                    ))

        return fn_list

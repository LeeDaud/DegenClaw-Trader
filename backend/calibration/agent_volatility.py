"""Agent 波动率追踪 — 按 Agent 历史波动动态缩放信号阈值"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)

# 波动率滚动窗口
_DEFAULT_WINDOW_MINUTES = 60
_DECAY_FACTOR = 0.9
# 缩放范围 [0.5x, 3.0x]
_MIN_SCALE = 0.5
_MAX_SCALE = 3.0

# 新 Agent 默认波动率（取全市场历史中位数经验值）
_DEFAULT_RANK_VOLATILITY = 3.0
_DEFAULT_PNL_VOLATILITY = 5.0
_DEFAULT_WR_VOLATILITY = 4.0


def _weighted_std(values: list[float], weights: list[float] | None = None) -> float:
    """加权标准差"""
    n = len(values)
    if n < 2:
        return 0.0
    if weights is None:
        weights = [1.0] * n
    total_w = sum(weights)
    if total_w <= 0:
        return 0.0
    avg = sum(v * w for v, w in zip(values, weights)) / total_w
    variance = sum(w * (v - avg) ** 2 for v, w in zip(values, weights)) / total_w
    return math.sqrt(variance)


def scaled_threshold(
    base_threshold: float,
    volatility: float,
    market_median_volatility: float,
    min_scale: float = _MIN_SCALE,
    max_scale: float = _MAX_SCALE,
) -> float:
    """按 Agent 波动率缩放阈值

    volatility / market_median 的比值决定缩放倍数，
    高波动 Agent 阈值放大（减少误报），低波动 Agent 阈值缩小（提高灵敏度）。
    """
    ref = market_median_volatility if market_median_volatility > 0 else 1.0
    ratio = volatility / ref
    scaled = base_threshold * ratio
    return max(base_threshold * min_scale, min(scaled, base_threshold * max_scale))


def normalized_score(raw_score: float, volatility: float, base_volatility: float = 3.0) -> float:
    """将原始分数归一化到标准波动率下的等效分数

    高波动 Agent 的分数降权，低波动 Agent 的分数加权，
    使综合信号评分中不同 Agent 可比。
    """
    ref = volatility if volatility > 0 else base_volatility
    return raw_score * (base_volatility / ref)


class AgentVolatilityTracker:
    """Agent 指标波动率追踪器

    每个 Agent 维护滚动窗口的排名/PnL/胜率波动率，
    用于动态缩放信号阈值。
    """

    def __init__(
        self,
        database: Database,
        window_minutes: int = _DEFAULT_WINDOW_MINUTES,
        decay_factor: float = _DECAY_FACTOR,
    ) -> None:
        self.db = database
        self.window_minutes = window_minutes
        self.decay_factor = decay_factor
        self._cache: dict[str, dict[str, float]] = {}  # agent_id -> {metric: volatility}

    def _fetch_window_snapshots(self, agent_id: str) -> list[dict[str, Any]]:
        """获取滚动窗口内的快照"""
        from datetime import datetime, timedelta, timezone

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)).isoformat().replace("+00:00", "Z")
        # 多取一些，确保有足够数据计算波动率
        snapshots = self.db.get_agent_snapshots(agent_id, limit=50)
        return [s for s in snapshots if s.get("snapshot_at", "") >= cutoff]

    def _calc_rank_volatility(self, snapshots: list[dict[str, Any]]) -> float:
        """计算排名波动率 — 相邻快照排名差值的加权标准差"""
        diffs = []
        for i in range(len(snapshots) - 1):
            d = abs(int(snapshots[i].get("rank", 0) or 0) - int(snapshots[i + 1].get("rank", 0) or 0))
            diffs.append(float(d))
        if len(diffs) < 2:
            return 0.0
        weights = [self.decay_factor ** (len(diffs) - i) for i in range(len(diffs))]
        return _weighted_std(diffs, weights)

    def _calc_pnl_volatility(self, snapshots: list[dict[str, Any]]) -> float:
        """计算 PnL 波动率 — 24h PnL 差值的加权标准差"""
        diffs = []
        for i in range(len(snapshots) - 1):
            pnl_i = float(snapshots[i].get("pnl_24h", 0) or 0)
            pnl_next = float(snapshots[i + 1].get("pnl_24h", 0) or 0)
            diffs.append(abs(pnl_i - pnl_next))
        if len(diffs) < 2:
            return 0.0
        weights = [self.decay_factor ** (len(diffs) - i) for i in range(len(diffs))]
        return _weighted_std(diffs, weights)

    def _calc_wr_volatility(self, snapshots: list[dict[str, Any]]) -> float:
        """计算胜率波动率 — 胜率差值的加权标准差"""
        diffs = []
        for i in range(len(snapshots) - 1):
            wr_i = float(snapshots[i].get("win_rate", 0) or 0)
            wr_next = float(snapshots[i + 1].get("win_rate", 0) or 0)
            diffs.append(abs(wr_i - wr_next))
        if len(diffs) < 2:
            return 0.0
        weights = [self.decay_factor ** (len(diffs) - i) for i in range(len(diffs))]
        return _weighted_std(diffs, weights)

    def refresh(self, agent_ids: list[str] | None = None) -> None:
        """刷新指定（或全部）Agent 的波动率缓存"""
        if agent_ids is None:
            all_agents = self.db.list_agents(limit=500)
            agent_ids = [a["agent_id"] for a in all_agents]

        for aid in agent_ids:
            snapshots = self._fetch_window_snapshots(aid)
            if len(snapshots) < 3:
                # 数据不足，用默认值
                self._cache[aid] = {
                    "rank_volatility": _DEFAULT_RANK_VOLATILITY,
                    "pnl_volatility": _DEFAULT_PNL_VOLATILITY,
                    "wr_volatility": _DEFAULT_WR_VOLATILITY,
                }
                continue

            self._cache[aid] = {
                "rank_volatility": self._calc_rank_volatility(snapshots),
                "pnl_volatility": self._calc_pnl_volatility(snapshots),
                "wr_volatility": self._calc_wr_volatility(snapshots),
            }

    def get_volatility(self, agent_id: str, metric: str = "rank") -> float:
        """获取 Agent 指定指标的波动率

        metric: "rank" | "pnl" | "wr"
        """
        key = f"{metric}_volatility"
        if agent_id in self._cache and key in self._cache[agent_id]:
            val = self._cache[agent_id][key]
            if val > 0:
                return val
        # 按指标返回默认值
        defaults = {"rank": _DEFAULT_RANK_VOLATILITY, "pnl": _DEFAULT_PNL_VOLATILITY, "wr": _DEFAULT_WR_VOLATILITY}
        return defaults.get(metric, _DEFAULT_RANK_VOLATILITY)

    def get_all_volatilities(self) -> dict[str, dict[str, float]]:
        """返回所有缓存的 Agent 波动率"""
        return dict(self._cache)

    def get_market_median_volatility(self, metric: str = "rank") -> float:
        """全市场该指标波动率中位数

        排除 volatility=0 的异常值（数据不足的 Agent）。
        """
        key = f"{metric}_volatility"
        values = [
            v[key] for v in self._cache.values()
            if key in v and v[key] > 0
        ]
        if not values:
            defaults = {"rank": _DEFAULT_RANK_VOLATILITY, "pnl": _DEFAULT_PNL_VOLATILITY, "wr": _DEFAULT_WR_VOLATILITY}
            return defaults.get(metric, _DEFAULT_RANK_VOLATILITY)
        values.sort()
        return values[len(values) // 2]

    def get_scaled_threshold(
        self,
        agent_id: str,
        metric: str,
        base_threshold: float,
    ) -> float:
        """获取 Agent 该指标的缩放后阈值"""
        vol = self.get_volatility(agent_id, metric)
        market_vol = self.get_market_median_volatility(metric)
        return scaled_threshold(base_threshold, vol, market_vol)

    def get_normalized_score(self, agent_id: str, raw_score: float, base_volatility: float = 3.0) -> float:
        """获取 Agent 该分数的标准化值"""
        vol = self.get_volatility(agent_id, "rank")
        return normalized_score(raw_score, vol, base_volatility)

    def clear_cache(self) -> None:
        """清空缓存（用于强制刷新）"""
        self._cache.clear()

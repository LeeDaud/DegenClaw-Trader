"""信号方向状态管理器 — 集中管理方向确认计数、EMA 平滑、推送冷却"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

EntityType = Literal["agent", "sub_pot"]
Direction = Literal["bullish", "bearish"]


@dataclass
class SignalDirectionState:
    """单个实体的方向状态"""
    entity_id: str
    entity_type: EntityType
    consecutive_readings: list[str] = field(default_factory=list)  # 方向读数历史
    ema_score: float = 0.0  # EMA 平滑分数
    last_notified_direction: Direction | None = None
    last_notified_at: float = 0.0  # time.monotonic()
    last_reading_at: float = 0.0  # time.monotonic()


DEFAULT_CONFIG = {
    "confirmation_count": 3,    # 连续 N 次同方向才确认
    "ema_alpha": 0.3,           # EMA 平滑系数
    "direction_cooldown": 1800, # 方向冷却：相反方向推送间隔（秒）
    "global_cooldown": 21600,   # 全局冷却：同一实体推送间隔（秒）
    "state_ttl": 86400,          # 状态 TTL：超过此时间无更新的实体自动清理
}


class SignalStateManager:
    """集中式信号方向状态管理器

    三大职责：
    1. 方向确认计数 — 连续 N 次同方向读数才确认
    2. EMA 分数平滑 — 抑制单次异常数据的影响
    3. 方向推送冷却 — 阻止在同一实体上推送相反方向
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = {**DEFAULT_CONFIG, **(config or {})}
        self._states: dict[str, SignalDirectionState] = {}
        self._last_cleanup: float = 0.0

    # ── 公共 API ──────────────────────────────────────────────────

    def record_reading(
        self,
        entity_id: str,
        entity_type: EntityType,
        direction: Direction | None,
        score: float = 0.0,
    ) -> tuple[bool, Direction | None, float]:
        """记录一次方向读数

        Args:
            entity_id: 实体 ID（agent_id / sub_pot_id）
            entity_type: 实体类型
            direction: 本次读数方向（None 表示中性/未知，不累计计数器）
            score: 原始分数（用于 EMA 平滑）

        Returns:
            (confirmed, final_direction, ema_score)
            confirmed=True 表示方向已确认（连续同方向达到 confirmation_count）
        """
        self._lazy_cleanup()

        state = self._get_or_create(entity_id, entity_type)
        now = time.monotonic()

        # 更新 EMA
        state.ema_score = self._update_ema(state.ema_score, score)

        if direction is None:
            # 中性读数：不累计方向计数器
            state.consecutive_readings = []
            state.last_reading_at = now
            return (False, None, state.ema_score)

        # 方向计数器
        if state.consecutive_readings and state.consecutive_readings[-1] != direction:
            # 方向变化 → 重置
            state.consecutive_readings = [direction]
            logger.debug("方向翻转: %s 从 %s → %s (重置计数器)",
                         entity_id, state.consecutive_readings[-2] if len(state.consecutive_readings) > 1 else "unknown", direction)
        else:
            state.consecutive_readings.append(direction)
            # 保留最近 confirmation_count 条即可
            max_len = self._config["confirmation_count"]
            if len(state.consecutive_readings) > max_len:
                state.consecutive_readings = state.consecutive_readings[-max_len:]

        state.last_reading_at = now

        confirmed = len(state.consecutive_readings) >= self._config["confirmation_count"]
        ema_adjusted = self._apply_ema_to_direction(state, direction, confirmed)

        if confirmed:
            logger.debug("方向确认: %s = %s (连续 %d 次, ema_score=%.2f)",
                         entity_id, direction, len(state.consecutive_readings), state.ema_score)

        return (confirmed, ema_adjusted, state.ema_score)

    def can_notify(self, entity_id: str, direction: Direction) -> bool:
        """检查是否允许推送该方向的通知

        检查项：
        1. 方向冷却 — 上次推送相反方向且距现在 < direction_cooldown
        2. 全局冷却 — 距上次推送 < global_cooldown

        Args:
            entity_id: 实体 ID
            direction: 计划推送的方向

        Returns:
            True 表示允许推送
        """
        state = self._states.get(entity_id)
        if state is None:
            return True

        now = time.monotonic()
        cfg = self._config

        # 方向冷却
        if (state.last_notified_direction is not None
                and state.last_notified_direction != direction
                and now - state.last_notified_at < cfg["direction_cooldown"]):
            remaining = int(cfg["direction_cooldown"] - (now - state.last_notified_at))
            logger.info("方向冷却命中: %s 上次推送 %s, 还需 %ds 才能推送 %s",
                        entity_id, state.last_notified_direction, remaining, direction)
            return False

        # 全局冷却
        if now - state.last_notified_at < cfg["global_cooldown"]:
            remaining = int(cfg["global_cooldown"] - (now - state.last_notified_at))
            logger.debug("全局冷却命中: %s 距上次推送 %ds 未到 %ds",
                         entity_id, int(now - state.last_notified_at), cfg["global_cooldown"])
            return False

        return True

    def mark_notified(self, entity_id: str, direction: Direction) -> None:
        """记录推送事件

        Args:
            entity_id: 实体 ID
            direction: 推送的方向
        """
        state = self._states.get(entity_id)
        if state is None:
            return

        now = time.monotonic()
        state.last_notified_direction = direction
        state.last_notified_at = now
        # 推送后重置方向计数器
        state.consecutive_readings = []
        logger.info("推送已记录: %s = %s", entity_id, direction)

    def get_smoothed_score(self, entity_id: str, raw_score: float) -> float:
        """获取 EMA 平滑后的分数

        如果实体尚无 EMA 值，直接返回 raw_score。
        """
        state = self._states.get(entity_id)
        if state is None or state.ema_score == 0.0:
            return raw_score
        return state.ema_score

    def update_config(self, key: str, value: Any) -> None:
        """运行时更新配置（用于自动调参）"""
        if key in self._config:
            old = self._config[key]
            self._config[key] = value
            logger.info("配置更新: %s = %s (was %s)", key, value, old)

    def get_config(self, key: str, default: Any = None) -> Any:
        """读取运行时配置"""
        return self._config.get(key, default)

    def reset(self, entity_id: str) -> None:
        """重置实体状态（用于测试或异常恢复）"""
        self._states.pop(entity_id, None)

    def get_state_count(self) -> int:
        """返回当前管理的实体数量"""
        return len(self._states)

    # ── 内部方法 ───────────────────────────────────────────────────

    def _get_or_create(self, entity_id: str, entity_type: EntityType) -> SignalDirectionState:
        if entity_id not in self._states:
            self._states[entity_id] = SignalDirectionState(
                entity_id=entity_id,
                entity_type=entity_type,
            )
        return self._states[entity_id]

    def _update_ema(self, prev_ema: float, raw_score: float) -> float:
        """更新 EMA 分数"""
        if prev_ema == 0.0:
            return raw_score
        alpha = self._config["ema_alpha"]
        return alpha * raw_score + (1 - alpha) * prev_ema

    def _apply_ema_to_direction(
        self,
        state: SignalDirectionState,
        direction: Direction,
        confirmed: bool,
    ) -> Direction | None:
        """根据 EMA 分数做方向微调（保留扩展点，当前直接返回原始方向）"""
        return direction

    def _lazy_cleanup(self) -> None:
        """惰性清理过期状态（每 100 次调用检查一次）"""
        now = time.monotonic()
        if now - self._last_cleanup < 3600.0:  # 每小时清理一次
            return

        ttl = self._config["state_ttl"]
        stale = [
            eid for eid, s in self._states.items()
            if s.last_reading_at > 0 and now - s.last_reading_at > ttl
        ]
        for eid in stale:
            del self._states[eid]

        if stale:
            logger.debug("状态清理: 移除 %d 个过期实体", len(stale))

        self._last_cleanup = now

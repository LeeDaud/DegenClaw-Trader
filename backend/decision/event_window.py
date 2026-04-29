"""事件窗口管理器 — 根据 DegenClaw 周期切换交易模式"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# 窗口类型
WINDOW_PRE_SELECTION = "pre_selection"
WINDOW_RESULT_CONFIRMATION = "result_confirmation"
WINDOW_COPY_TRADING = "copy_trading"
WINDOW_POT_PERFORMANCE = "pot_performance"
WINDOW_RISK_EXIT = "risk_exit"

# 窗口顺序（用于不可逆推进）
_WINDOW_ORDER = [
    WINDOW_PRE_SELECTION,
    WINDOW_RESULT_CONFIRMATION,
    WINDOW_COPY_TRADING,
    WINDOW_POT_PERFORMANCE,
    WINDOW_RISK_EXIT,
]

ACTION_WATCH = "watch"
ACTION_PROBE_BUY = "probe_buy"
ACTION_CONFIRM_BUY = "confirm_buy"
ACTION_HOLD = "hold"
ACTION_REDUCE = "reduce"
ACTION_SELL_OR_EXIT = "sell_or_exit"
ACTION_BLOCK_TRADE = "block_trade"

ALL_ACTIONS = [
    ACTION_WATCH, ACTION_PROBE_BUY, ACTION_CONFIRM_BUY,
    ACTION_HOLD, ACTION_REDUCE, ACTION_SELL_OR_EXIT, ACTION_BLOCK_TRADE,
]

# 各窗口配置
_WINDOW_CONFIGS = {
    WINDOW_PRE_SELECTION: {
        "risk_level": "medium",
        "allowed_actions": [ACTION_WATCH, ACTION_PROBE_BUY, ACTION_HOLD],
        "position_multiplier": 0.7,
    },
    WINDOW_RESULT_CONFIRMATION: {
        "risk_level": "medium",
        "allowed_actions": [ACTION_WATCH, ACTION_PROBE_BUY, ACTION_HOLD],
        "position_multiplier": 0.5,
    },
    WINDOW_COPY_TRADING: {
        "risk_level": "low",
        "allowed_actions": [ACTION_WATCH, ACTION_PROBE_BUY, ACTION_CONFIRM_BUY, ACTION_HOLD],
        "position_multiplier": 1.0,
    },
    WINDOW_POT_PERFORMANCE: {
        "risk_level": "low",
        "allowed_actions": [ACTION_WATCH, ACTION_HOLD, ACTION_REDUCE, ACTION_SELL_OR_EXIT],
        "position_multiplier": 1.0,
    },
    WINDOW_RISK_EXIT: {
        "risk_level": "high",
        "allowed_actions": [ACTION_WATCH, ACTION_REDUCE, ACTION_SELL_OR_EXIT],
        "position_multiplier": 0.3,
    },
}


@dataclass
class EventWindow:
    """当前事件窗口状态"""
    window: str  # 窗口类型
    risk_level: str  # low / medium / high
    allowed_actions: list[str]  # 允许的交易动作
    position_multiplier: float  # 仓位乘数

    def allows(self, action: str) -> bool:
        return action in self.allowed_actions


def _get_monday(d: date) -> date:
    """返回 d 所在周的周一"""
    return d - timedelta(days=d.weekday())


class EventWindowManager:
    """事件窗口管理器"""

    def __init__(self) -> None:
        self._forced_window: str | None = None

    def force_window(self, window: str | None) -> None:
        """强制锁定窗口（用于测试或手动覆盖）"""
        if window is not None and window not in _WINDOW_ORDER:
            raise ValueError(f"无效窗口: {window}")
        self._forced_window = window

    def get_current_window(self, today: date | None = None) -> EventWindow:
        """返回当前所在的事件窗口"""
        if self._forced_window:
            return self._build_window(self._forced_window)

        today = today or date.today()
        monday = _get_monday(today)
        days_since_monday = (today - monday).days  # 0=Mon .. 6=Sun

        # 周一公布日
        if days_since_monday == 0:
            window_name = WINDOW_RESULT_CONFIRMATION
        # 周二 ~ 周四：copy_trading
        elif days_since_monday <= 3:
            window_name = WINDOW_COPY_TRADING
        # 周五 ~ 周六：pot_performance
        elif days_since_monday <= 5:
            window_name = WINDOW_POT_PERFORMANCE
        # 周日：risk_exit
        else:
            window_name = WINDOW_RISK_EXIT

        # 如果是周一二且距离周一不足 1 天，可能是 pre_selection
        # （在实际系统中，pre_selection 发生在周一前 3 天，即上周五~周日）
        if days_since_monday < 0:
            window_name = WINDOW_PRE_SELECTION

        return self._build_window(window_name)

    def get_window_for_date(self, dt: date) -> str:
        """返回给定日期对应的窗口名称"""
        monday = _get_monday(dt)
        days_since_monday = (dt - monday).days

        if days_since_monday == 0:
            return WINDOW_RESULT_CONFIRMATION
        elif days_since_monday <= 3:
            return WINDOW_COPY_TRADING
        elif days_since_monday <= 5:
            return WINDOW_POT_PERFORMANCE
        else:
            return WINDOW_RISK_EXIT

    def is_action_allowed(self, action: str, today: date | None = None) -> bool:
        """检查某个动作在当前窗口是否被允许"""
        return self.get_current_window(today).allows(action)

    def _build_window(self, name: str) -> EventWindow:
        cfg = _WINDOW_CONFIGS.get(name, _WINDOW_CONFIGS[WINDOW_PRE_SELECTION])
        return EventWindow(
            window=name,
            risk_level=cfg["risk_level"],
            allowed_actions=list(cfg["allowed_actions"]),
            position_multiplier=cfg["position_multiplier"],
        )

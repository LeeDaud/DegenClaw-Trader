"""交易决策引擎 — 评分 → 交易信号"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from decision.event_window import EventWindow, EventWindowManager

logger = logging.getLogger(__name__)

# 信号动作
ACTION_WATCH = "watch"
ACTION_PROBE_BUY = "probe_buy"
ACTION_CONFIRM_BUY = "confirm_buy"
ACTION_HOLD = "hold"
ACTION_REDUCE = "reduce"
ACTION_SELL_OR_EXIT = "sell_or_exit"
ACTION_BLOCK_TRADE = "block_trade"

# 置信度
CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

# 信号状态
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXECUTED = "executed"
STATUS_EXPIRED = "expired"


@dataclass
class DecisionInput:
    """决策引擎输入"""
    agent_id: str
    agent_name: str
    token_address: str

    # 评分数据
    score_total: int
    council_score: int
    trading_score: int
    rank_trend_score: int
    token_market_score: int
    risk_penalty: int

    # Agent 状态
    rank: int
    rank_change_1h: int
    rank_change_24h: int
    is_top_10: bool
    is_selected: bool

    # Token 市场
    price_usd: float
    liquidity_usd: float
    volume_24h: float
    price_change_24h: float
    buy_slippage: float

    # 持仓状态（有持仓时才设置）
    has_position: bool = False
    position_entry_price: float = 0.0
    position_pnl_pct: float = 0.0

    # 策略质量指标
    win_rate: float = 0.0
    win_rate_change: float = 0.0  # 多快照趋势变动（百分点）

    # 额外数据（透传用）
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TradeSignal:
    """交易信号"""
    signal_id: str
    agent_id: str
    token_address: str
    action: str
    confidence: str
    reason: str
    key_factors: list[str]

    # 交易参数
    max_position_usdc: float
    slippage_limit_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    time_exit_hours: int

    # 风控检查
    risk_checks: dict[str, bool]

    # 元数据
    window: str
    status: str = STATUS_PENDING
    created_at: str = ""
    expires_at: str = ""


def _score_confidence(total: int) -> str:
    if total >= 80:
        return CONFIDENCE_HIGH
    if total >= 70:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_LOW


def _calc_position(action: str, score_total: int, liquidity_usd: float, position_multiplier: float) -> float:
    """计算建议仓位（USDC）"""
    # 基础仓位假设 200 USDC
    base = 200.0

    # probe_buy 用 25%
    if action == ACTION_PROBE_BUY:
        base *= 0.25
    elif action == ACTION_CONFIRM_BUY:
        base *= 0.8

    # 事件窗口调节
    base *= position_multiplier

    # 评分调节 (60-100 -> 0.5x-1.5x)
    score_mult = 0.5 + max(0, score_total - 60) / 40.0
    base *= min(score_mult, 1.5)

    # 流动性限制：不超过流动性的 5%
    liquidity_cap = liquidity_usd * 0.05

    return min(base, liquidity_cap)


def _calc_exit_params(action: str) -> tuple[float, float, int]:
    """计算止损止盈和时间退出参数"""
    if action == ACTION_PROBE_BUY:
        return 12.0, 35.0, 36
    if action == ACTION_CONFIRM_BUY:
        return 10.0, 40.0, 72
    return 15.0, 30.0, 48


class TradingDecisionEngine:
    """交易决策引擎"""

    def __init__(self, event_window_manager: EventWindowManager | None = None) -> None:
        self.window_manager = event_window_manager or EventWindowManager()

    def decide(self, inp: DecisionInput, window: EventWindow | None = None) -> TradeSignal:
        """执行一轮决策，返回交易信号"""
        if window is None:
            window = self.window_manager.get_current_window()

        now = datetime.now(timezone.utc)
        signal_id = f"sig_{now.strftime('%Y%m%d_%H%M%S')}_{inp.agent_id[:8]}"
        created_at = now.isoformat()

        key_factors: list[str] = []
        risk_checks: dict[str, bool] = {}

        # --- 基础风控检查 ---
        liquidity_ok = inp.liquidity_usd >= 20000
        slippage_ok = inp.buy_slippage == 0 or inp.buy_slippage < 3
        holder_concentration_ok = True  # 暂缺 holder 数据
        daily_loss_limit_ok = True  # 暂缺日亏损追踪
        event_window_ok = True

        risk_checks = {
            "liquidity_ok": liquidity_ok,
            "slippage_ok": slippage_ok,
            "holder_concentration_ok": holder_concentration_ok,
            "daily_loss_limit_ok": daily_loss_limit_ok,
            "event_window_ok": event_window_ok,
        }

        # --- 决策逻辑 ---

        # Step 1: 总分过低 → watch
        if inp.score_total < 60:
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_WATCH, CONFIDENCE_LOW,
                f"总分 {inp.score_total} 低于 60，仅观察",
                ["score_too_low"],
                risk_checks,
            )

        # Step 2: 极端风险 → block_trade
        if not liquidity_ok or not slippage_ok:
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_BLOCK_TRADE, CONFIDENCE_HIGH,
                "风控检查未通过",
                ["liquidity_risk", "slippage_risk"],
                risk_checks,
            )

        # Step 3: 已持仓 → 检查退出条件
        if inp.has_position:
            # 止损 / 止盈 / 时间退出
            if inp.position_pnl_pct <= -12:
                return self._make_signal(
                    inp, window, signal_id, created_at,
                    ACTION_SELL_OR_EXIT, CONFIDENCE_HIGH,
                    f"止损触发: PnL {inp.position_pnl_pct:.1f}%",
                    ["stop_loss"],
                    risk_checks,
                )
            if inp.position_pnl_pct >= 35:
                return self._make_signal(
                    inp, window, signal_id, created_at,
                    ACTION_SELL_OR_EXIT, CONFIDENCE_MEDIUM,
                    f"止盈触发: PnL {inp.position_pnl_pct:.1f}%",
                    ["take_profit"],
                    risk_checks,
                )

            # 评分下降 / 排名恶化 / 策略恶化 → reduce
            reduce_triggers: list[str] = []
            if inp.rank_change_24h < -5 and inp.risk_penalty <= -5:
                reduce_triggers.append("排名恶化")
            if inp.win_rate_change < -5:
                reduce_triggers.append("胜率下滑")

            if len(reduce_triggers) >= 1:
                return self._make_signal(
                    inp, window, signal_id, created_at,
                    ACTION_REDUCE, CONFIDENCE_MEDIUM,
                    f"{'+'.join(reduce_triggers)}，建议减仓",
                    reduce_triggers + ["high_risk"],
                    risk_checks,
                )

            # 条件正常 → hold
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_HOLD, _score_confidence(inp.score_total),
                "持仓正常，继续持有",
                ["score_stable"],
                risk_checks,
            )

        # Step 4: probe_buy 条件检查
        # 核心：评分优质 + 排名合适 + win_rate 趋势向好
        if (
            inp.score_total >= 75
            and 11 <= inp.rank <= 25
            and inp.rank_change_24h > 0
            and inp.win_rate_change > -2  # win_rate 未显著下滑
            and inp.volume_24h > 1000
            and inp.buy_slippage < 2
            and inp.price_change_24h < 150
            and window.allows(ACTION_PROBE_BUY)
        ):
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_PROBE_BUY, CONFIDENCE_MEDIUM,
                f"评分优质 + 排名 {inp.rank} + win_rate 趋势 {inp.win_rate_change:+.1f}pp，建议小仓试探",
                ["score_good", "rank_rising", "win_rate_improving", "volume_active", "slippage_ok"],
                risk_checks,
            )

        # Step 5: confirm_buy 条件检查
        # win_rate 显著改善 + 排名持续上升 + 流动性充足
        if (
            inp.score_total >= 80
            and inp.rank_change_1h > 0
            and inp.rank_change_24h >= 3
            and inp.win_rate_change >= 3  # win_rate 明显改善
            and inp.volume_24h > 20000
            and inp.buy_slippage < 1
            and inp.price_change_24h < 100
            and liquidity_ok
            and window.allows(ACTION_CONFIRM_BUY)
        ):
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_CONFIRM_BUY, CONFIDENCE_HIGH,
                f"高评分 + 排名持续上升 + 流动性充足，建议建仓",
                ["score_high", "rank_momentum", "liquidity_ok", "momentum_confirmed"],
                risk_checks,
            )

        # Step 6: 排名和流动性恶化 → reduce
        if inp.rank_change_24h < -10 and not inp.has_position:
            return self._make_signal(
                inp, window, signal_id, created_at,
                ACTION_REDUCE, CONFIDENCE_LOW,
                "排名大幅下滑，建议减仓或等待",
                ["rank_dropping"],
                risk_checks,
            )

        # 默认 → watch
        return self._make_signal(
            inp, window, signal_id, created_at,
            ACTION_WATCH, CONFIDENCE_LOW,
            "条件不满足，继续观察",
            ["conditions_not_met"],
            risk_checks,
        )

    def _make_signal(
        self,
        inp: DecisionInput,
        window: EventWindow,
        signal_id: str,
        created_at: str,
        action: str,
        confidence: str,
        reason: str,
        key_factors: list[str],
        risk_checks: dict[str, bool],
    ) -> TradeSignal:
        """构建 TradeSignal"""
        stop_loss, take_profit, time_exit = _calc_exit_params(action)
        position = _calc_position(action, inp.score_total, inp.liquidity_usd, window.position_multiplier)

        return TradeSignal(
            signal_id=signal_id,
            agent_id=inp.agent_id,
            token_address=inp.token_address,
            action=action,
            confidence=confidence,
            reason=reason,
            key_factors=key_factors,
            max_position_usdc=round(position, 2),
            slippage_limit_pct=inp.buy_slippage if inp.buy_slippage > 0 else 1.0,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            time_exit_hours=time_exit,
            risk_checks=risk_checks,
            window=window.window,
            status=STATUS_PENDING,
            created_at=created_at,
            expires_at="",
        )

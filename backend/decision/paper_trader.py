"""Paper Trading 模拟交易模块"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """模拟持仓"""
    position_id: str
    signal_id: str
    agent_id: str
    token_address: str

    action: str  # probe_buy / confirm_buy
    entry_price: float
    amount_token: float
    cost_usdc: float
    entry_slippage: float
    entered_at: str

    # 当前状态
    current_price: float = 0.0
    unrealized_pnl: float = 0.0

    # 退出
    exit_price: float | None = None
    realized_pnl: float | None = None
    exit_slippage: float | None = None
    exited_at: str | None = None
    exit_reason: str | None = None

    # 止损止盈参数
    stop_loss_pct: float = 12.0
    take_profit_pct: float = 35.0
    time_exit_hours: int = 36

    status: str = "open"  # open / closed

    extra: dict[str, Any] = field(default_factory=dict)

    def as_record(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "signal_id": self.signal_id,
            "agent_id": self.agent_id,
            "token_address": self.token_address,
            "action": self.action,
            "entry_price": self.entry_price,
            "amount_token": self.amount_token,
            "cost_usdc": self.cost_usdc,
            "entry_slippage": self.entry_slippage,
            "entered_at": self.entered_at,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "exit_price": self.exit_price,
            "realized_pnl": self.realized_pnl,
            "exit_slippage": self.exit_slippage,
            "exited_at": self.exited_at,
            "exit_reason": self.exit_reason,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "time_exit_hours": self.time_exit_hours,
            "status": self.status,
        }

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> PaperPosition:
        return cls(
            position_id=record["position_id"],
            signal_id=record["signal_id"],
            agent_id=record["agent_id"],
            token_address=record["token_address"],
            action=record["action"],
            entry_price=record["entry_price"],
            amount_token=record["amount_token"],
            cost_usdc=record["cost_usdc"],
            entry_slippage=record["entry_slippage"],
            entered_at=record["entered_at"],
            current_price=record.get("current_price", 0),
            unrealized_pnl=record.get("unrealized_pnl", 0),
            exit_price=record.get("exit_price"),
            realized_pnl=record.get("realized_pnl"),
            exit_slippage=record.get("exit_slippage"),
            exited_at=record.get("exited_at"),
            exit_reason=record.get("exit_reason"),
            stop_loss_pct=record.get("stop_loss_pct", 12),
            take_profit_pct=record.get("take_profit_pct", 35),
            time_exit_hours=record.get("time_exit_hours", 36),
            status=record.get("status", "open"),
        )


def _simulate_slippage(market_slippage: float, order_size: float, liquidity: float) -> float:
    """模拟滑点：市场滑点 + 订单大小因子 + 随机因子"""
    if liquidity <= 0:
        return market_slippage * 1.3
    size_factor = order_size / max(liquidity, 1)
    random_factor = 0.7 + random.random() * 0.6  # 0.7 ~ 1.3
    return market_slippage * (1 + size_factor) * random_factor


class PaperTrader:
    """Paper Trading 模拟交易器"""

    def __init__(self) -> None:
        self._positions: dict[str, PaperPosition] = {}

    def execute_buy(
        self,
        signal_id: str,
        agent_id: str,
        token_address: str,
        action: str,
        max_position_usdc: float,
        price_usd: float,
        liquidity_usd: float,
        buy_slippage: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        time_exit_hours: int,
    ) -> PaperPosition | None:
        """模拟买入，返回持仓"""
        if price_usd <= 0 or liquidity_usd <= 0:
            logger.warning("无法买入: 价格或流动性无效")
            return None

        # 模拟滑点
        slippage = _simulate_slippage(buy_slippage, max_position_usdc, liquidity_usd)
        effective_price = price_usd * (1 + slippage / 100)
        amount_token = max_position_usdc / effective_price

        now = datetime.now(timezone.utc).isoformat()
        position_id = f"pp_{uuid4().hex[:12]}"

        position = PaperPosition(
            position_id=position_id,
            signal_id=signal_id,
            agent_id=agent_id,
            token_address=token_address,
            action=action,
            entry_price=effective_price,
            amount_token=amount_token,
            cost_usdc=max_position_usdc,
            entry_slippage=round(slippage, 4),
            entered_at=now,
            current_price=price_usd,
            unrealized_pnl=0.0,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            time_exit_hours=time_exit_hours,
            status="open",
        )

        self._positions[position_id] = position
        logger.info("paper buy: %s $%.2f @ %.6f (slippage=%.2f%%)", agent_id, max_position_usdc, effective_price, slippage)
        return position

    def execute_sell(
        self,
        position: PaperPosition,
        price_usd: float,
        liquidity_usd: float,
        sell_slippage: float,
        exit_reason: str,
    ) -> PaperPosition:
        """模拟卖出，平仓"""
        if position.status == "closed":
            return position

        slippage = _simulate_slippage(sell_slippage, position.cost_usdc, liquidity_usd)
        effective_price = price_usd * (1 - slippage / 100)
        proceeds = position.amount_token * effective_price
        realized_pnl = proceeds - position.cost_usdc
        realized_pnl_pct = (realized_pnl / position.cost_usdc) * 100 if position.cost_usdc > 0 else 0

        now = datetime.now(timezone.utc).isoformat()
        position.exit_price = effective_price
        position.realized_pnl = round(realized_pnl, 2)
        position.exit_slippage = round(slippage, 4)
        position.exited_at = now
        position.exit_reason = exit_reason
        position.status = "closed"
        position.current_price = price_usd
        position.unrealized_pnl = 0.0

        logger.info("paper sell: %s PnL=%.2f USDC (%.2f%%) reason=%s", position.agent_id, realized_pnl, realized_pnl_pct, exit_reason)
        return position

    def update_price(self, position: PaperPosition, current_price: float) -> PaperPosition:
        """更新持仓当前价格和浮动盈亏"""
        if position.status == "closed":
            return position
        position.current_price = current_price
        position.unrealized_pnl = round((current_price - position.entry_price) * position.amount_token, 2)
        return position

    def check_exit_conditions(self, position: PaperPosition, current_price: float) -> str | None:
        """检查是否触发了退出条件"""
        if position.status == "closed":
            return None

        pnl_pct = ((current_price - position.entry_price) / position.entry_price) * 100

        # 止损
        if pnl_pct <= -position.stop_loss_pct:
            return "stop_loss"

        # 止盈
        if pnl_pct >= position.take_profit_pct:
            return "take_profit"

        # 时间退出
        if position.entered_at:
            try:
                entered = datetime.fromisoformat(position.entered_at)
                elapsed = (datetime.now(timezone.utc) - entered).total_seconds() / 3600
                if elapsed >= position.time_exit_hours:
                    return "time_exit"
            except ValueError:
                pass

        return None

    def get_open_positions(self) -> list[PaperPosition]:
        return [p for p in self._positions.values() if p.status == "open"]

    def get_closed_positions(self) -> list[PaperPosition]:
        return [p for p in self._positions.values() if p.status == "closed"]

    def get_all_positions(self) -> list[PaperPosition]:
        return list(self._positions.values())

    def get_position(self, position_id: str) -> PaperPosition | None:
        return self._positions.get(position_id)

    def load_positions(self, positions: list[PaperPosition]) -> None:
        for p in positions:
            self._positions[p.position_id] = p

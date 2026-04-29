from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_event_id() -> str:
    return f"evt_{uuid4().hex[:16]}"


def is_valid_evm_address(addr: str) -> bool:
    if not addr.startswith("0x"):
        return False
    if len(addr) != 42:
        return False
    try:
        int(addr[2:], 16)
        return True
    except ValueError:
        return False


# --- Agent 模型 ---

@dataclass(slots=True)
class Agent:
    agent_id: str
    name: str
    profile_url: str
    token_address: str
    chain: str
    created_at: str
    updated_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> Agent:
        return cls(
            agent_id=row["agent_id"],
            name=row["name"],
            profile_url=row["profile_url"],
            token_address=row["token_address"],
            chain=row["chain"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(slots=True)
class AgentSnapshot:
    agent_id: str
    rank: int
    pnl_24h: float
    pnl_7d: float
    win_rate: float
    max_drawdown: float
    trade_count: int
    is_top_10: bool
    is_selected: bool
    snapshot_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


# --- Token 模型 ---

@dataclass(slots=True)
class Token:
    token_address: str
    symbol: str
    name: str
    pool_address: str
    chain: str
    created_at: str
    updated_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> Token:
        return cls(
            token_address=row["token_address"],
            symbol=row["symbol"],
            name=row["name"],
            pool_address=row["pool_address"],
            chain=row["chain"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(slots=True)
class TokenMarketSnapshot:
    token_address: str
    price_usd: float
    liquidity_usd: float
    volume_1h: float
    volume_24h: float
    price_change_1h: float
    price_change_24h: float
    buy_slippage: float
    sell_slippage: float
    holder_count: int
    top_10_holder_pct: float
    snapshot_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


# --- 排行榜快照 ---

@dataclass(slots=True)
class LeaderboardSnapshot:
    snapshot_at: str
    raw_data: str  # JSON string

    def as_record(self) -> dict[str, Any]:
        return {"snapshot_at": self.snapshot_at, "raw_data": self.raw_data}


# --- AI Pot ---

@dataclass(slots=True)
class AIPotRound:
    round_id: str
    round_start: str
    round_end: str
    status: str  # upcoming / active / ended
    selected_agents: str  # JSON list
    pot_pnl: float
    created_at: str
    updated_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    def selected_agent_list(self) -> list[str]:
        try:
            return json.loads(self.selected_agents)
        except (json.JSONDecodeError, TypeError):
            return []

    @classmethod
    def from_row(cls, row: Any) -> AIPotRound:
        return cls(
            round_id=row["round_id"],
            round_start=row["round_start"],
            round_end=row["round_end"],
            status=row["status"],
            selected_agents=row["selected_agents"],
            pot_pnl=float(row["pot_pnl"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# --- 评分 ---

@dataclass(slots=True)
class AgentScore:
    agent_id: str
    token_address: str
    score_total: int
    council_probability_score: int
    trading_performance_score: int
    rank_trend_score: int
    token_market_score: int
    visibility_score: int
    risk_penalty: int
    grade: str  # A / B / C / D / E / F
    label: str
    reason: str  # 评分原因文本
    scored_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


# --- 交易信号 ---


@dataclass(slots=True)
class TradeSignalModel:
    signal_id: str
    agent_id: str
    token_address: str
    agent_name: str
    action: str
    confidence: str
    reason: str
    key_factors: str  # JSON list
    max_position_usdc: float
    slippage_limit_pct: float
    stop_loss_pct: float
    take_profit_pct: float
    time_exit_hours: int
    risk_checks: str  # JSON dict
    window: str
    status: str
    created_at: str
    expires_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PaperPositionModel:
    position_id: str
    signal_id: str
    agent_id: str
    token_address: str
    action: str
    entry_price: float
    amount_token: float
    cost_usdc: float
    entry_slippage: float
    entered_at: str
    current_price: float
    unrealized_pnl: float
    exit_price: float
    realized_pnl: float
    exit_slippage: float
    exited_at: str
    exit_reason: str
    stop_loss_pct: float
    take_profit_pct: float
    time_exit_hours: int
    status: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


# --- 系统事件 ---

@dataclass(slots=True)
class Alert:
    alert_id: str
    agent_id: str
    agent_name: str
    alert_type: str  # surge / dump / volume_spike / rank_surge / rank_dump
    severity: str    # low / medium / high / critical
    title: str
    detail: str
    score: float
    snapshot_data: str  # JSON — 触发时的上下文快照
    notified: bool
    created_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SystemEvent:
    event_id: str
    module: str
    level: str
    event: str
    detail: str
    trace_id: str
    created_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

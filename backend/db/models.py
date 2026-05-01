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
    token_symbol: str
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
            token_symbol=row.get("token_symbol", ""),
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
    last_trade_at: str
    total_realized_pnl: float
    snapshot_at: str

    @classmethod
    def from_row(cls, row: Any) -> AgentSnapshot:
        return cls(
            agent_id=row["agent_id"],
            rank=row["rank"],
            pnl_24h=row["pnl_24h"],
            pnl_7d=row["pnl_7d"],
            win_rate=row["win_rate"],
            max_drawdown=row["max_drawdown"],
            trade_count=row["trade_count"],
            is_top_10=bool(row["is_top_10"]),
            is_selected=bool(row["is_selected"]),
            last_trade_at=row.get("last_trade_at", ""),
            total_realized_pnl=row.get("total_realized_pnl", 0.0),
            snapshot_at=row["snapshot_at"],
        )

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
    # 以下为后期新增字段（有默认值，兼容旧库）
    season_id: str = ""
    total_capital: float = 0.0
    total_current_value: float = 0.0
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    return_pct: float = 0.0
    raw_data: str = "{}"

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
            season_id=row.get("season_id", ""),
            total_capital=float(row.get("total_capital", 0)),
            total_current_value=float(row.get("total_current_value", 0)),
            total_realized_pnl=float(row.get("total_realized_pnl", 0)),
            total_unrealized_pnl=float(row.get("total_unrealized_pnl", 0)),
            return_pct=float(row.get("return_pct", 0)),
            raw_data=row.get("raw_data", "{}"),
        )


@dataclass(slots=True)
class PotSubAgent:
    """AI Pot 子池（每个 pot 持有 10 个子池）"""
    round_id: str
    sub_pot_id: str
    name: str
    status: str
    agent_id: str
    agent_name: str
    token_address: str
    token_symbol: str
    starting_capital: float
    current_value: float
    realized_pnl: float
    unrealized_pnl: float
    final_pnl: float
    positions: str  # JSON
    snapshot_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> PotSubAgent:
        return cls(
            round_id=row["round_id"],
            sub_pot_id=row["sub_pot_id"],
            name=row["name"],
            status=row["status"],
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            token_address=row["token_address"],
            token_symbol=row["token_symbol"],
            starting_capital=float(row["starting_capital"]),
            current_value=float(row["current_value"]),
            realized_pnl=float(row["realized_pnl"]),
            unrealized_pnl=float(row["unrealized_pnl"]),
            final_pnl=float(row["final_pnl"]),
            positions=row["positions"],
            snapshot_at=row["snapshot_at"],
        )


@dataclass(slots=True)
class CouncilEvaluation:
    """AI 评委会评选数据"""
    season_id: str
    season_name: str
    pot_size: float
    total_agents_analyzed: int
    consensus_agents: str  # JSON
    model_verdicts: str    # JSON
    raw_data: str          # JSON
    fetched_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> CouncilEvaluation:
        return cls(
            season_id=row["season_id"],
            season_name=row.get("season_name", ""),
            pot_size=float(row.get("pot_size", 0)),
            total_agents_analyzed=int(row.get("total_agents_analyzed", 0)),
            consensus_agents=row.get("consensus_agents", "[]"),
            model_verdicts=row.get("model_verdicts", "{}"),
            raw_data=row.get("raw_data", "{}"),
            fetched_at=row["fetched_at"],
        )


@dataclass(slots=True)
class CouncilAgentScore:
    """评委会对单个 agent 的打分"""
    season_id: str
    evaluation_id: int
    agent_name: str
    rank: int
    votes: int
    per_model_rationale: str  # JSON: {"modelName": "rationale..."}
    created_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PotPnlSnapshot:
    """子池 PnL 快照（用于监控变化）"""
    sub_pot_id: str
    round_id: str
    current_value: float
    realized_pnl: float
    unrealized_pnl: float
    final_pnl: float
    snapshot_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> PotPnlSnapshot:
        return cls(
            sub_pot_id=row["sub_pot_id"],
            round_id=row["round_id"],
            current_value=float(row["current_value"]),
            realized_pnl=float(row["realized_pnl"]),
            unrealized_pnl=float(row["unrealized_pnl"]),
            final_pnl=float(row["final_pnl"]),
            snapshot_at=row["snapshot_at"],
        )


@dataclass(slots=True)
class CouncilLeaderboardScore:
    """AgentList 中展示的评委会分数映射"""
    agent_id: str
    season_id: str
    council_rank: int
    council_score: float
    council_votes: int
    fetched_at: str

    def as_record(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: Any) -> CouncilLeaderboardScore:
        return cls(
            agent_id=row["agent_id"],
            season_id=row["season_id"],
            council_rank=int(row.get("council_rank", 0)),
            council_score=float(row.get("council_score", 0)),
            council_votes=int(row.get("council_votes", 0)),
            fetched_at=row["fetched_at"],
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

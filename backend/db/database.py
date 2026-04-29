from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from db.models import Agent, AgentScore, AgentSnapshot, Token, TokenMarketSnapshot, Alert, SystemEvent, AIPotRound, LeaderboardSnapshot, TradeSignalModel, PaperPositionModel


TABLES_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0.0,
    snapshot_data TEXT NOT NULL DEFAULT '{}',
    notified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    profile_url TEXT NOT NULL DEFAULT '',
    token_address TEXT NOT NULL DEFAULT '',
    token_symbol TEXT NOT NULL DEFAULT '',
    chain TEXT NOT NULL DEFAULT 'base',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    rank INTEGER NOT NULL DEFAULT 0,
    pnl_24h REAL NOT NULL DEFAULT 0.0,
    pnl_7d REAL NOT NULL DEFAULT 0.0,
    win_rate REAL NOT NULL DEFAULT 0.0,
    max_drawdown REAL NOT NULL DEFAULT 0.0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    is_top_10 INTEGER NOT NULL DEFAULT 0,
    is_selected INTEGER NOT NULL DEFAULT 0,
    last_trade_at TEXT NOT NULL DEFAULT '',
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    pool_address TEXT NOT NULL DEFAULT '',
    chain TEXT NOT NULL DEFAULT 'base',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL,
    price_usd REAL NOT NULL DEFAULT 0.0,
    liquidity_usd REAL NOT NULL DEFAULT 0.0,
    volume_1h REAL NOT NULL DEFAULT 0.0,
    volume_24h REAL NOT NULL DEFAULT 0.0,
    price_change_1h REAL NOT NULL DEFAULT 0.0,
    price_change_24h REAL NOT NULL DEFAULT 0.0,
    buy_slippage REAL NOT NULL DEFAULT 0.0,
    sell_slippage REAL NOT NULL DEFAULT 0.0,
    holder_count INTEGER NOT NULL DEFAULT 0,
    top_10_holder_pct REAL NOT NULL DEFAULT 0.0,
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leaderboard_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT NOT NULL,
    raw_data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_pot_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id TEXT NOT NULL UNIQUE,
    round_start TEXT NOT NULL,
    round_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    selected_agents TEXT NOT NULL DEFAULT '[]',
    pot_pnl REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    token_address TEXT NOT NULL DEFAULT '',
    score_total INTEGER NOT NULL DEFAULT 0,
    council_probability_score INTEGER NOT NULL DEFAULT 0,
    trading_performance_score INTEGER NOT NULL DEFAULT 0,
    rank_trend_score INTEGER NOT NULL DEFAULT 0,
    token_market_score INTEGER NOT NULL DEFAULT 0,
    visibility_score INTEGER NOT NULL DEFAULT 0,
    risk_penalty INTEGER NOT NULL DEFAULT 0,
    grade TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT 'ignore',
    reason TEXT NOT NULL DEFAULT '',
    scored_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    module TEXT NOT NULL,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    token_address TEXT NOT NULL DEFAULT '',
    agent_name TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'low',
    reason TEXT NOT NULL DEFAULT '',
    key_factors TEXT NOT NULL DEFAULT '[]',
    max_position_usdc REAL NOT NULL DEFAULT 0,
    slippage_limit_pct REAL NOT NULL DEFAULT 1.0,
    stop_loss_pct REAL NOT NULL DEFAULT 12,
    take_profit_pct REAL NOT NULL DEFAULT 35,
    time_exit_hours INTEGER NOT NULL DEFAULT 48,
    risk_checks TEXT NOT NULL DEFAULT '{}',
    window TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL UNIQUE,
    signal_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    token_address TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entry_price REAL NOT NULL DEFAULT 0,
    amount_token REAL NOT NULL DEFAULT 0,
    cost_usdc REAL NOT NULL DEFAULT 0,
    entry_slippage REAL NOT NULL DEFAULT 0,
    entered_at TEXT NOT NULL,
    current_price REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    exit_price REAL NOT NULL DEFAULT 0,
    realized_pnl REAL NOT NULL DEFAULT 0,
    exit_slippage REAL NOT NULL DEFAULT 0,
    exited_at TEXT NOT NULL DEFAULT '',
    exit_reason TEXT NOT NULL DEFAULT '',
    stop_loss_pct REAL NOT NULL DEFAULT 12,
    take_profit_pct REAL NOT NULL DEFAULT 35,
    time_exit_hours INTEGER NOT NULL DEFAULT 48,
    status TEXT NOT NULL DEFAULT 'open'
);
"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_agents_agent_id ON agents(agent_id);
CREATE INDEX IF NOT EXISTS idx_agents_token ON agents(token_address);
CREATE INDEX IF NOT EXISTS idx_snapshots_agent_time ON agent_snapshots(agent_id, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_tokens_address ON tokens(token_address);
CREATE INDEX IF NOT EXISTS idx_market_snapshots_token_time ON token_market_snapshots(token_address, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_time ON system_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_module ON system_events(module);
CREATE INDEX IF NOT EXISTS idx_scores_agent_scored ON agent_scores(agent_id, scored_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_total ON agent_scores(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_pot_rounds_status ON ai_pot_rounds(status);
CREATE INDEX IF NOT EXISTS idx_leaderboard_time ON leaderboard_snapshots(snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_agent ON alerts(agent_id);
CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_notified ON alerts(notified);
CREATE INDEX IF NOT EXISTS idx_signals_agent ON trade_signals(agent_id);
CREATE INDEX IF NOT EXISTS idx_signals_time ON trade_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON trade_signals(status);
CREATE INDEX IF NOT EXISTS idx_positions_agent ON paper_positions(agent_id);
CREATE INDEX IF NOT EXISTS idx_positions_status ON paper_positions(status);
"""


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(TABLES_SQL)
            conn.executescript(INDEXES_SQL)
            # 迁移：兼容已有数据库
            for col in ["grade", "reason"]:
                try:
                    conn.execute(f"ALTER TABLE agent_scores ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute("ALTER TABLE agents ADD COLUMN token_symbol TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE agent_snapshots ADD COLUMN last_trade_at TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    # --- Agent ---

    def upsert_agent(self, agent: Agent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agents(agent_id, name, profile_url, token_address, token_symbol, chain, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name = excluded.name,
                    profile_url = excluded.profile_url,
                    token_address = excluded.token_address,
                    token_symbol = excluded.token_symbol,
                    chain = excluded.chain,
                    updated_at = excluded.updated_at
                """,
                (agent.agent_id, agent.name, agent.profile_url, agent.token_address,
                 agent.token_symbol, agent.chain, agent.created_at, agent.updated_at),
            )
            conn.commit()

    def list_agents(self, limit: int = 50, offset: int = 0,
                    season_start: str | None = None, season_end: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if season_start and season_end:
                rows = conn.execute(
                    """SELECT a.* FROM agents a
                        INNER JOIN (
                            SELECT agent_id, rank, last_trade_at, ROW_NUMBER() OVER (
                                PARTITION BY agent_id ORDER BY snapshot_at DESC
                            ) rn FROM agent_snapshots
                        ) s ON a.agent_id = s.agent_id AND s.rn = 1
                        WHERE s.last_trade_at != ''
                          AND s.last_trade_at >= ?
                          AND s.last_trade_at <= ?
                        ORDER BY COALESCE(s.rank, 999999) ASC
                        LIMIT ? OFFSET ?""",
                    (season_start, season_end, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT a.* FROM agents a
                        LEFT JOIN (
                            SELECT agent_id, rank, ROW_NUMBER() OVER (
                                PARTITION BY agent_id ORDER BY snapshot_at DESC
                            ) rn FROM agent_snapshots
                        ) s ON a.agent_id = s.agent_id AND s.rn = 1
                        ORDER BY COALESCE(s.rank, 999999) ASC
                        LIMIT ? OFFSET ?""",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def count_agents(self, season_start: str | None = None, season_end: str | None = None) -> int:
        with self._connect() as conn:
            if season_start and season_end:
                return conn.execute(
                    """SELECT COUNT(*) FROM agents a
                        INNER JOIN (
                            SELECT agent_id, last_trade_at, ROW_NUMBER() OVER (
                                PARTITION BY agent_id ORDER BY snapshot_at DESC
                            ) rn FROM agent_snapshots
                        ) s ON a.agent_id = s.agent_id AND s.rn = 1
                        WHERE s.last_trade_at != ''
                          AND s.last_trade_at >= ?
                          AND s.last_trade_at <= ?""",
                    (season_start, season_end),
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]

    # --- Agent Snapshot ---

    def insert_agent_snapshots(self, snapshots: list[AgentSnapshot]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO agent_snapshots(agent_id, rank, pnl_24h, pnl_7d, win_rate, max_drawdown,
                                            trade_count, is_top_10, is_selected, last_trade_at, snapshot_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (s.agent_id, s.rank, s.pnl_24h, s.pnl_7d, s.win_rate, s.max_drawdown,
                     s.trade_count, int(s.is_top_10), int(s.is_selected), s.last_trade_at, s.snapshot_at)
                    for s in snapshots
                ],
            )
            conn.commit()

    def get_agent_latest_snapshot(self, agent_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM agent_snapshots WHERE agent_id = ? ORDER BY snapshot_at DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_agent_snapshots(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_snapshots WHERE agent_id = ? ORDER BY snapshot_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Token ---

    def upsert_token(self, token: Token) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tokens(token_address, symbol, name, pool_address, chain, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token_address) DO UPDATE SET
                    symbol = excluded.symbol,
                    name = excluded.name,
                    pool_address = excluded.pool_address,
                    chain = excluded.chain,
                    updated_at = excluded.updated_at
                """,
                (token.token_address, token.symbol, token.name, token.pool_address,
                 token.chain, token.created_at, token.updated_at),
            )
            conn.commit()

    def get_token(self, token_address: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tokens WHERE token_address = ?", (token_address,)).fetchone()
        return dict(row) if row else None

    def list_tokens(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tokens ORDER BY token_address LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    # --- Token Market Snapshot ---

    def insert_market_snapshots(self, snapshots: list[TokenMarketSnapshot]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO token_market_snapshots(token_address, price_usd, liquidity_usd, volume_1h, volume_24h,
                    price_change_1h, price_change_24h, buy_slippage, sell_slippage,
                    holder_count, top_10_holder_pct, snapshot_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (s.token_address, s.price_usd, s.liquidity_usd, s.volume_1h, s.volume_24h,
                     s.price_change_1h, s.price_change_24h, s.buy_slippage, s.sell_slippage,
                     s.holder_count, s.top_10_holder_pct, s.snapshot_at)
                    for s in snapshots
                ],
            )
            conn.commit()

    def get_latest_market_snapshot(self, token_address: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM token_market_snapshots WHERE token_address = ? ORDER BY snapshot_at DESC LIMIT 1",
                (token_address,),
            ).fetchone()
        return dict(row) if row else None

    def get_token_market_snapshots(self, token_address: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM token_market_snapshots WHERE token_address = ? ORDER BY snapshot_at DESC LIMIT ?",
                (token_address, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Leaderboard Snapshot ---

    def insert_leaderboard_snapshot(self, snapshot: LeaderboardSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO leaderboard_snapshots(snapshot_at, raw_data) VALUES(?, ?)",
                (snapshot.snapshot_at, snapshot.raw_data),
            )
            conn.commit()

    def list_leaderboard_snapshots(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM leaderboard_snapshots ORDER BY snapshot_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- AI Pot Round ---

    def upsert_ai_pot_round(self, pot_round: AIPotRound) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ai_pot_rounds(round_id, round_start, round_end, status, selected_agents, pot_pnl, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(round_id) DO UPDATE SET
                    round_start = excluded.round_start,
                    round_end = excluded.round_end,
                    status = excluded.status,
                    selected_agents = excluded.selected_agents,
                    pot_pnl = excluded.pot_pnl,
                    updated_at = excluded.updated_at
                """,
                (pot_round.round_id, pot_round.round_start, pot_round.round_end,
                 pot_round.status, pot_round.selected_agents, pot_round.pot_pnl,
                 pot_round.created_at, pot_round.updated_at),
            )
            conn.commit()

    def get_active_ai_pot_round(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ai_pot_rounds WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def list_ai_pot_rounds(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_pot_rounds ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Agent Score ---

    def insert_agent_score(self, score: AgentScore) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_scores(agent_id, token_address, score_total,
                    council_probability_score, trading_performance_score, rank_trend_score,
                    token_market_score, visibility_score, risk_penalty, grade, label, reason, scored_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (score.agent_id, score.token_address, score.score_total,
                 score.council_probability_score, score.trading_performance_score, score.rank_trend_score,
                 score.token_market_score, score.visibility_score, score.risk_penalty,
                 score.grade, score.label, score.reason, score.scored_at),
            )
            conn.commit()

    def list_agent_scores(self, limit: int = 50, offset: int = 0,
                          agent_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            parts = ["SELECT * FROM agent_scores WHERE 1=1"]
            params: list[Any] = []
            if agent_id:
                parts.append("AND agent_id = ?")
                params.append(agent_id)
            parts.append("ORDER BY scored_at DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])
            rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    def get_agent_score_history(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_scores WHERE agent_id = ? ORDER BY scored_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- System Events ---

    def insert_alert(self, alert: Alert) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO alerts(alert_id, agent_id, agent_name, alert_type, severity,
                        title, detail, score, snapshot_data, notified, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (alert.alert_id, alert.agent_id, alert.agent_name, alert.alert_type, alert.severity,
                     alert.title, alert.detail, alert.score, alert.snapshot_data, int(alert.notified), alert.created_at),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    def list_alerts(self, limit: int = 50, offset: int = 0,
                    alert_type: str | None = None, agent_id: str | None = None,
                    unread_only: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn:
            parts = ["SELECT * FROM alerts WHERE 1=1"]
            params: list[Any] = []
            if alert_type:
                parts.append("AND alert_type = ?")
                params.append(alert_type)
            if agent_id:
                parts.append("AND agent_id = ?")
                params.append(agent_id)
            if unread_only:
                parts.append("AND notified = 0")
            parts.append("ORDER BY created_at DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])
            rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    def count_unread_alerts(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM alerts WHERE notified = 0").fetchone()[0]

    def mark_alert_notified(self, alert_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE alerts SET notified = 1 WHERE alert_id = ?", (alert_id,))
            conn.commit()

    # --- System Events ---

    def insert_system_event(self, event: SystemEvent) -> None:
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO system_events(event_id, module, level, event, detail, trace_id, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event.event_id, event.module, event.level, event.event,
                     event.detail, event.trace_id, event.created_at),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    def list_system_events(self, limit: int = 50, offset: int = 0,
                           module: str | None = None, level: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            parts = ["SELECT * FROM system_events WHERE 1=1"]
            params: list[Any] = []
            if module:
                parts.append("AND module = ?")
                params.append(module)
            if level:
                parts.append("AND level = ?")
                params.append(level)
            parts.append("ORDER BY created_at DESC LIMIT ? OFFSET ?")
            params.extend([limit, offset])
            rows = conn.execute(" ".join(parts), params).fetchall()
        return [dict(r) for r in rows]

    # --- Dashboard ---

    def get_dashboard_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            latest_snapshot = conn.execute(
                "SELECT snapshot_at FROM agent_snapshots ORDER BY snapshot_at DESC LIMIT 1"
            ).fetchone()
            active_pot = conn.execute(
                "SELECT * FROM ai_pot_rounds WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            recent_events = conn.execute(
                "SELECT * FROM system_events ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            top_movers = conn.execute(
                """
                SELECT a.agent_id, a.name,
                       COALESCE(s1.rank - s2.rank, 0) as rank_change,
                       s1.rank, s2.rank as prev_rank
                FROM agents a
                JOIN agent_snapshots s1 ON s1.id = (
                    SELECT id FROM agent_snapshots WHERE agent_id = a.agent_id
                    ORDER BY snapshot_at DESC LIMIT 1
                )
                LEFT JOIN agent_snapshots s2 ON s2.id = (
                    SELECT id FROM agent_snapshots WHERE agent_id = a.agent_id
                    ORDER BY snapshot_at DESC LIMIT 1 OFFSET 1
                )
                ORDER BY rank_change DESC LIMIT 5
                """
            ).fetchall()
            recent_signals = conn.execute(
                "SELECT * FROM agent_scores ORDER BY scored_at DESC LIMIT 5"
            ).fetchall()

        return {
            "agent_count": agent_count,
            "last_collect_time": latest_snapshot["snapshot_at"] if latest_snapshot else None,
            "active_pot_round": dict(active_pot) if active_pot else None,
            "recent_events": [dict(r) for r in recent_events],
            "top_movers": [dict(r) for r in top_movers],
            "recent_signals": [dict(r) for r in recent_signals],
        }

    # --- Trade Signals ---

    def insert_trade_signal(self, signal: TradeSignalModel) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trade_signals(signal_id, agent_id, token_address, agent_name,
                    action, confidence, reason, key_factors, max_position_usdc,
                    slippage_limit_pct, stop_loss_pct, take_profit_pct, time_exit_hours,
                    risk_checks, window, status, created_at, expires_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (signal.signal_id, signal.agent_id, signal.token_address, signal.agent_name,
                 signal.action, signal.confidence, signal.reason, signal.key_factors,
                 signal.max_position_usdc, signal.slippage_limit_pct, signal.stop_loss_pct,
                 signal.take_profit_pct, signal.time_exit_hours, signal.risk_checks,
                 signal.window, signal.status, signal.created_at, signal.expires_at),
            )
            conn.commit()

    def list_trade_signals(
        self, limit: int = 50, offset: int = 0, status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM trade_signals WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trade_signals ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_signal(self, signal_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trade_signals WHERE signal_id = ?", (signal_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_signal_status(self, signal_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE trade_signals SET status = ? WHERE signal_id = ?",
                (status, signal_id),
            )
            conn.commit()

    # --- Paper Positions ---

    def insert_paper_position(self, pos: PaperPositionModel) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_positions(position_id, signal_id, agent_id, token_address,
                    action, entry_price, amount_token, cost_usdc, entry_slippage, entered_at,
                    current_price, unrealized_pnl, exit_price, realized_pnl, exit_slippage,
                    exited_at, exit_reason, stop_loss_pct, take_profit_pct, time_exit_hours, status)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pos.position_id, pos.signal_id, pos.agent_id, pos.token_address,
                 pos.action, pos.entry_price, pos.amount_token, pos.cost_usdc,
                 pos.entry_slippage, pos.entered_at, pos.current_price, pos.unrealized_pnl,
                 pos.exit_price, pos.realized_pnl, pos.exit_slippage, pos.exited_at,
                 pos.exit_reason, pos.stop_loss_pct, pos.take_profit_pct,
                 pos.time_exit_hours, pos.status),
            )
            conn.commit()

    def update_paper_position(self, pos: PaperPositionModel) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE paper_positions SET current_price=?, unrealized_pnl=?,
                    exit_price=?, realized_pnl=?, exit_slippage=?, exited_at=?,
                    exit_reason=?, status=?
                WHERE position_id=?
                """,
                (pos.current_price, pos.unrealized_pnl, pos.exit_price, pos.realized_pnl,
                 pos.exit_slippage, pos.exited_at, pos.exit_reason, pos.status,
                 pos.position_id),
            )
            conn.commit()

    def list_paper_positions(
        self, limit: int = 50, offset: int = 0, status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM paper_positions WHERE status = ? ORDER BY entered_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_positions ORDER BY entered_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_paper_position(self, position_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM paper_positions WHERE position_id = ?", (position_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_open_paper_positions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_positions WHERE status = 'open' ORDER BY entered_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

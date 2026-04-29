# 数据库 Schema 草案 (V0)

> 基于 Phase 0 调研结果，遵循 PRD 和 DATABASE-SCHEMA.md 的设计。
> 使用 SQLite + aiosqlite（复用 OKX-Robot 和 SignalHub 的技术选型）。

---

## 设计原则

1. 所有快照表使用 `snapshot_at` 作为时间索引
2. `agent_id` 和 `token_address` 作为核心关联键
3. 价格使用 REAL，金额使用 REAL，百分比使用 REAL
4. 所有表包含 `id` INTEGER PRIMARY KEY AUTOINCREMENT 和 `created_at` TEXT

---

## 表 1: agents — Agent 主表

```sql
CREATE TABLE IF NOT EXISTS agents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER UNIQUE NOT NULL,     -- Virtuals API 的 id
    uid             TEXT,                          -- Virtuals API 的 uid
    name            TEXT NOT NULL,
    symbol          TEXT,
    description     TEXT,
    status          TEXT DEFAULT 'unknown',        -- UNDERGRAD / ACTIVE / TRADING
    category        TEXT,
    chain           TEXT DEFAULT 'BASE',
    level           INTEGER DEFAULT 1,
    factory         TEXT,
    creator_address TEXT,
    image_url       TEXT,
    created_at      TEXT NOT NULL,                 -- 记录创建时间
    updated_at      TEXT NOT NULL                  -- 最后一次更新
);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_name ON agents(name);
```

**说明：** Agent 主信息。从 Virtuals API 获取，定时更新。

---

## 表 2: token_addresses — Token 地址映射

```sql
CREATE TABLE IF NOT EXISTS token_addresses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    token_address   TEXT,                          -- 正式 Token 地址（launched 后非空）
    pre_token       TEXT,                          -- 预售 Token 地址
    pre_token_pair  TEXT,                          -- 预售池地址
    lp_address      TEXT,                          -- 流动性池地址
    total_supply    INTEGER DEFAULT 1000000000,
    chain           TEXT DEFAULT 'BASE',
    first_seen_at   TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX idx_token_addresses_agent ON token_addresses(agent_id);
CREATE INDEX idx_token_addresses_token ON token_addresses(token_address);
CREATE INDEX idx_token_addresses_pre ON token_addresses(pre_token);
```

**说明：** 一个 Agent 可能经历 preToken → tokenAddress 的迁移。保留完整记录。

---

## 表 3: market_snapshots — 市场数据快照

```sql
CREATE TABLE IF NOT EXISTS market_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id                INTEGER NOT NULL REFERENCES agents(agent_id),
    token_address           TEXT,                    -- 快照时的 token 地址
    liquidity_usd           REAL DEFAULT 0,
    volume_24h              REAL DEFAULT 0,
    net_volume_24h          REAL DEFAULT 0,
    price_change_percent_24h REAL DEFAULT 0,
    mcap_in_virtual         REAL DEFAULT 0,
    fdv_in_virtual          REAL DEFAULT 0,
    holder_count            INTEGER DEFAULT 0,
    top10_holder_percentage REAL DEFAULT 0,
    holder_count_pct_24h    REAL DEFAULT 0,
    dev_holding_percentage  REAL DEFAULT 0,
    value_fx                REAL DEFAULT 0,
    snapshot_at             TEXT NOT NULL             -- 快照时间
);
CREATE INDEX idx_market_snapshots_agent ON market_snapshots(agent_id, snapshot_at);
CREATE INDEX idx_market_snapshots_time ON market_snapshots(snapshot_at);
```

**说明：** 定时快照表，记录每个 Agent 在每个时间点的市场数据。

---

## 表 4: degenclaw_rankings — DegenClaw 排名数据（claw-api 鉴权解决后启用）

```sql
CREATE TABLE IF NOT EXISTS degenclaw_rankings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    rank            INTEGER,                        -- 当前排名
    previous_rank   INTEGER,                        -- 上期排名
    rank_change_1h  INTEGER,                        -- 1h 排名变化
    rank_change_24h INTEGER,                        -- 24h 排名变化
    pnl_24h         REAL,                           -- 24h PnL
    pnl_7d          REAL,                           -- 7d PnL
    win_rate        REAL,                           -- 胜率
    max_drawdown    REAL,                           -- 最大回撤
    trade_count     INTEGER,                        -- 交易次数
    snapshot_at     TEXT NOT NULL
);
CREATE INDEX idx_degenclaw_rankings_agent ON degenclaw_rankings(agent_id, snapshot_at);
CREATE INDEX idx_degenclaw_rankings_rank ON degenclaw_rankings(rank, snapshot_at);
```

**说明：** DegenClaw 排行榜数据。需要 claw-api JWT 鉴权。

---

## 表 5: ai_pot_rounds — AI Pot Round 数据

```sql
CREATE TABLE IF NOT EXISTS ai_pot_rounds (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id            INTEGER UNIQUE NOT NULL,
    round_start         TEXT,                        -- Round 开始时间
    round_end           TEXT,                        -- Round 结束时间
    announcement_time   TEXT,                        -- Council 公布时间
    selected_agent_ids  TEXT,                        -- JSON array of agent IDs
    pot_pnl             REAL,                        -- Pot 总盈亏
    status              TEXT DEFAULT 'pending',      -- pending / active / completed
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_ai_pot_rounds_status ON ai_pot_rounds(status);
```

**说明：** AI Pot 竞赛轮次信息。需要 claw-api 鉴权或手动录入。

---

## 表 6: agent_scores — 评分结果

```sql
CREATE TABLE IF NOT EXISTS agent_scores (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id                        INTEGER NOT NULL REFERENCES agents(agent_id),
    score_total                     INTEGER NOT NULL,  -- 0-100
    -- AI Council 入选概率评分 (0-35)
    council_probability_score       INTEGER DEFAULT 0,
    rank_to_score                   INTEGER DEFAULT 0,
    history_selection_bonus         INTEGER DEFAULT 0,
    rank_momentum_bonus             INTEGER DEFAULT 0,
    top20_stability_bonus           INTEGER DEFAULT 0,
    -- 交易表现评分 (0-20)
    trading_performance_score       INTEGER DEFAULT 0,
    pnl_improvement                 INTEGER DEFAULT 0,
    drawdown_score                  INTEGER DEFAULT 0,
    trade_frequency_stability       INTEGER DEFAULT 0,
    single_trade_dependency_penalty INTEGER DEFAULT 0,
    -- 排名趋势评分 (0-15)
    rank_trend_score                INTEGER DEFAULT 0,
    rank_change_1h                  INTEGER DEFAULT 0,
    rank_change_24h                 INTEGER DEFAULT 0,
    threshold_breakthrough          INTEGER DEFAULT 0,
    top10_drop_penalty              INTEGER DEFAULT 0,
    -- 市场质量评分 (0-15)
    token_market_score              INTEGER DEFAULT 0,
    liquidity_score                 INTEGER DEFAULT 0,
    volume_growth                   INTEGER DEFAULT 0,
    slippage_score                  INTEGER DEFAULT 0,
    holder_distribution             INTEGER DEFAULT 0,
    -- 注意力评分 (0-10)
    attention_score                 INTEGER DEFAULT 0,
    -- 风险扣分 (0-20)
    risk_penalty                    INTEGER DEFAULT 0,
    -- 标签与推荐
    label                           TEXT,              -- hot_candidate / candidate / high_watch / watch / ignore / risk_alert
    recommended_action              TEXT,              -- probe_buy / confirm_buy / hold / reduce / sell_or_exit / watch / block_trade
    reasons                         TEXT,              -- JSON array of reason strings
    risk_warnings                   TEXT,              -- JSON array of warning strings
    scored_at                       TEXT NOT NULL      -- 评分时间
);
CREATE INDEX idx_agent_scores_agent ON agent_scores(agent_id, scored_at);
CREATE INDEX idx_agent_scores_total ON agent_scores(score_total DESC);
CREATE INDEX idx_agent_scores_label ON agent_scores(label);
```

**说明：** 评分引擎的输出结果。定时（每小时）生成。

---

## 表 7: event_windows — 事件窗口记录

```sql
CREATE TABLE IF NOT EXISTS event_windows (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    window_type     TEXT NOT NULL,        -- pre_selection / result_confirmation / copy_trading / pot_performance / risk_exit
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    round_id        INTEGER,             -- 关联 AI Pot round
    risk_level      TEXT,                 -- low / medium / high
    position_multiplier REAL DEFAULT 1.0, -- 仓位乘数
    allowed_actions TEXT,                 -- JSON array
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_event_windows_type ON event_windows(window_type, started_at);
```

**说明：** 事件窗口的时间线和配置。

---

## 表 8: trade_signals — 交易信号

```sql
CREATE TABLE IF NOT EXISTS trade_signals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id           TEXT UNIQUE NOT NULL,  -- signal_YYYYMMDD_HHMMSS_XXX
    agent_id            INTEGER NOT NULL REFERENCES agents(agent_id),
    token_address       TEXT,
    action              TEXT NOT NULL,         -- probe_buy / confirm_buy / hold / reduce / sell_or_exit
    score               INTEGER NOT NULL,
    score_breakdown     TEXT,                  -- JSON
    position_size_usd   REAL,
    stop_loss_pct       REAL,
    take_profit_pct     REAL,
    time_exit_hours     REAL,
    event_window        TEXT,
    reason              TEXT,                  -- 信号理由（非空）
    risk_warnings       TEXT,                  -- JSON array
    status              TEXT DEFAULT 'pending', -- pending / pending_approval / approved / rejected / executing / executed / expired
    expires_at          TEXT,
    created_at          TEXT NOT NULL,
    executed_at         TEXT
);
CREATE INDEX idx_trade_signals_agent ON trade_signals(agent_id);
CREATE INDEX idx_trade_signals_status ON trade_signals(status);
CREATE INDEX idx_trade_signals_action ON trade_signals(action);
CREATE INDEX idx_trade_signals_created ON trade_signals(created_at DESC);
```

**说明：** 决策引擎输出的交易信号。

---

## 表 9: trade_orders — 交易订单

```sql
CREATE TABLE IF NOT EXISTS trade_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        TEXT UNIQUE NOT NULL,   -- ord_YYYYMMDD_HHMMSS_XXX
    signal_id       TEXT REFERENCES trade_signals(signal_id),
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    token_address   TEXT NOT NULL,
    side            TEXT NOT NULL,           -- buy / sell
    amount_usd      REAL,
    amount_token    TEXT,                    -- raw token amount
    status          TEXT DEFAULT 'pending',  -- pending / submitted / confirmed / closed / failed
    tx_hash         TEXT,
    entry_price     REAL,
    slippage        REAL,
    gas_fee         REAL,
    mode            TEXT DEFAULT 'paper',    -- paper / live
    created_at      TEXT NOT NULL,
    executed_at     TEXT,
    fail_reason     TEXT
);
CREATE INDEX idx_trade_orders_signal ON trade_orders(signal_id);
CREATE INDEX idx_trade_orders_status ON trade_orders(status);
CREATE INDEX idx_trade_orders_created ON trade_orders(created_at DESC);
```

**说明：** 执行层订单记录。参考 OKX-Robot `copy_trades` 表。

---

## 表 10: positions — 持仓

```sql
CREATE TABLE IF NOT EXISTS positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id     TEXT UNIQUE NOT NULL,
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    token_address   TEXT NOT NULL,
    order_id        TEXT REFERENCES trade_orders(order_id),
    entry_price     REAL NOT NULL,
    amount          REAL NOT NULL,
    current_price   REAL,
    unrealized_pnl  REAL,
    stop_loss       REAL,
    take_profit     REAL,
    time_exit_at    TEXT,
    status          TEXT DEFAULT 'open',     -- open / closed / liquidated
    mode            TEXT DEFAULT 'paper',    -- paper / live
    entered_at      TEXT NOT NULL,
    closed_at       TEXT,
    close_price     REAL,
    realized_pnl    REAL,
    roi_pct         REAL
);
CREATE INDEX idx_positions_agent ON positions(agent_id);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_positions_mode ON positions(mode);
```

**说明：** 持仓记录。Phase 3 为 paper trading，Phase 4+ 为真实持仓。

---

## 表 11: execution_logs — 执行日志

```sql
CREATE TABLE IF NOT EXISTS execution_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT REFERENCES trade_signals(signal_id),
    order_id        TEXT REFERENCES trade_orders(order_id),
    log_type        TEXT NOT NULL,           -- signal / risk_check / order / position / system
    level           TEXT DEFAULT 'info',     -- info / warning / error
    message         TEXT NOT NULL,
    details         TEXT,                    -- JSON
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_execution_logs_type ON execution_logs(log_type);
CREATE INDEX idx_execution_logs_created ON execution_logs(created_at DESC);
```

---

## 表 12: trade_reviews — 交易复盘

```sql
CREATE TABLE IF NOT EXISTS trade_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id       TEXT REFERENCES trade_signals(signal_id),
    order_id        TEXT REFERENCES trade_orders(order_id),
    position_id     TEXT REFERENCES positions(position_id),
    agent_id        INTEGER NOT NULL REFERENCES agents(agent_id),
    pnl             REAL,
    roi_pct         REAL,
    hold_hours      REAL,
    exit_reason     TEXT,                    -- stop_loss / take_profit / time_exit / manual / score_drop / rank_drop / liquidity_drop
    fail_reason     TEXT,                    -- 失败原因分类
    fail_category   TEXT,                    -- 追高 / 流动性不足 / 事件预期失败 / AI Council 未入选 / AI Pot 表现不佳 / 止损过窄 / 退出过早 / 数据延迟 / 执行失败 / 策略噪音
    lessons_learned TEXT,
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_trade_reviews_agent ON trade_reviews(agent_id);
CREATE INDEX idx_trade_reviews_category ON trade_reviews(fail_category);
```

---

## 表 13: scoring_config_versions — 评分配置版本管理

```sql
CREATE TABLE IF NOT EXISTS scoring_config_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL,
    config_yaml     TEXT NOT NULL,           -- 完整配置内容
    changelog       TEXT,                    -- 变更说明
    created_at      TEXT NOT NULL
);
CREATE INDEX idx_scoring_config_versions_version ON scoring_config_versions(version);
```

---

## 表 14: risk_events — 风控事件记录

```sql
CREATE TABLE IF NOT EXISTS risk_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,           -- daily_loss / consecutive_loss / frequency / interval / exposure / emergency_stop
    severity        TEXT DEFAULT 'warning',  -- info / warning / critical
    message         TEXT NOT NULL,
    details         TEXT,                    -- JSON
    is_active       INTEGER DEFAULT 1,      -- 1=active, 0=resolved
    auto_resolve_at TEXT,                    -- 自动恢复时间
    created_at      TEXT NOT NULL,
    resolved_at     TEXT
);
CREATE INDEX idx_risk_events_type ON risk_events(event_type);
CREATE INDEX idx_risk_events_active ON risk_events(is_active);
```

---

## 表 15: price_cache — 价格缓存

```sql
CREATE TABLE IF NOT EXISTS price_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address   TEXT NOT NULL,
    price_usd       REAL NOT NULL,
    source          TEXT DEFAULT 'virtuals',  -- virtuals / okx / rpc
    cached_at       TEXT NOT NULL
);
CREATE INDEX idx_price_cache_token ON price_cache(token_address, cached_at DESC);
```

---

## ER 关系

```
agents (1) ──→ token_addresses (N)
agents (1) ──→ market_snapshots (N)
agents (1) ──→ degenclaw_rankings (N)
agents (1) ──→ agent_scores (N)
agents (1) ──→ trade_signals (N)
agents (1) ──→ trade_orders (N)
agents (1) ──→ positions (N)
agents (1) ──→ trade_reviews (N)

trade_signals (1) ──→ trade_orders (N)
trade_orders (1) ──→ positions (1)
trade_orders (1) ──→ execution_logs (N)
positions (1) ──→ trade_reviews (1)

ai_pot_rounds (1) ──→ event_windows (N)
```

## 迁移策略

1. **Phase 1：** 创建 agents + token_addresses + market_snapshots（监控所需）
2. **Phase 2：** 添加 degenclaw_rankings + agent_scores + ai_pot_rounds
3. **Phase 3：** 添加 event_windows + trade_signals + 扩展 positions（paper）
4. **Phase 4：** 添加 trade_orders + 扩展 positions（live）+ execution_logs
5. **Phase 5：** 添加 risk_events + price_cache
6. **Phase 6：** 添加 trade_reviews + scoring_config_versions

# 数据库 Schema 详细设计

## 概述

第一阶段使用 SQLite（better-sqlite3），通过 Drizzle ORM 管理 schema。

数据库文件：`data/degenclaw.db`（路径由 .env 中 `DATABASE_PATH` 配置）

## Schema 完整定义

### 9.1 agents

Agent 基础信息表。

```typescript
import { sqliteTable, text, integer, real } from 'drizzle-orm/sqlite-core';

export const agents = sqliteTable('agents', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  agent_id: text('agent_id').notNull().unique(),
  name: text('name').notNull(),
  profile_url: text('profile_url'),
  token_address: text('token_address'),
  chain: text('chain').default('base'),
  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  updated_at: text('updated_at').notNull().default('CURRENT_TIMESTAMP'),
});
```

**索引：** `agent_id` (UNIQUE), `token_address`

### 9.2 agent_snapshots

Agent 排名和表现快照。

```typescript
export const agentSnapshots = sqliteTable('agent_snapshots', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  agent_id: text('agent_id').notNull().references(() => agents.agent_id),
  rank: integer('rank').notNull(),
  pnl_24h: real('pnl_24h'),           // 百分比，如 12.5 = +12.5%
  pnl_7d: real('pnl_7d'),
  win_rate: real('win_rate'),          // 0-100
  max_drawdown: real('max_drawdown'),  // 百分比
  trade_count: integer('trade_count'),
  is_top_10: integer('is_top_10', { mode: 'boolean' }).default(false),
  is_selected: integer('is_selected', { mode: 'boolean' }).default(false),
  snapshot_at: text('snapshot_at').notNull(),
});
```

**索引：** `(agent_id, snapshot_at)`, `(rank, snapshot_at)`

### 9.3 tokens

Token 基础信息。

```typescript
export const tokens = sqliteTable('tokens', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  token_address: text('token_address').notNull().unique(),
  symbol: text('symbol'),
  name: text('name'),
  pool_address: text('pool_address'),
  chain: text('chain').default('base'),
  decimals: integer('decimals').default(18),
  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  updated_at: text('updated_at').notNull().default('CURRENT_TIMESTAMP'),
});
```

**索引：** `token_address` (UNIQUE)

### 9.4 token_market_snapshots

Token 市场数据快照。

```typescript
export const tokenMarketSnapshots = sqliteTable('token_market_snapshots', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  token_address: text('token_address').notNull().references(() => tokens.token_address),
  price_usd: real('price_usd'),
  price_virtual: real('price_virtual'),    // Virtuals 平台价格（如有）
  liquidity_usd: real('liquidity_usd'),     // DEX 流动性
  volume_1h: real('volume_1h'),             // 1 小时成交量（USD）
  volume_24h: real('volume_24h'),           // 24 小时成交量（USD）
  price_change_1h: real('price_change_1h'), // 百分比
  price_change_24h: real('price_change_24h'), // 百分比
  buy_slippage: real('buy_slippage'),       // 100 USDC 买入滑点百分比
  sell_slippage: real('sell_slippage'),     // 100 USDC 卖出滑点百分比
  holder_count: integer('holder_count'),
  top_10_holder_pct: real('top_10_holder_pct'), // top 10 holder 占比
  fdv: real('fdv'),                          // Fully Diluted Valuation
  pair_created_at: text('pair_created_at'),  // 交易对创建时间
  snapshot_at: text('snapshot_at').notNull(),
});
```

**索引：** `(token_address, snapshot_at)`

### 9.5 leaderboard_snapshots

排行榜原始快照（DegenClaw 排行榜的完整快照）。

```typescript
export const leaderboardSnapshots = sqliteTable('leaderboard_snapshots', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  snapshot_data: text('snapshot_data').notNull(),  // JSON，完整的排行榜数据
  agent_count: integer('agent_count').notNull(),
  source: text('source').default('degenclaw'),
  snapshot_at: text('snapshot_at').notNull(),
});
```

**用途：** 保留原始数据以便后续重新计算或回溯

### 9.6 ai_pot_rounds

AI Pot 轮次信息。

```typescript
export const aiPotRounds = sqliteTable('ai_pot_rounds', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  round_id: text('round_id').notNull().unique(),
  round_start: text('round_start').notNull(),   // ISO datetime
  round_end: text('round_end').notNull(),       // ISO datetime
  status: text('status').notNull().default('upcoming'),  // upcoming | active | ended
  selected_agents: text('selected_agents'),     // JSON array of agent IDs
  pot_pnl: real('pot_pnl'),                     // AI Pot 整体 PnL
  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  updated_at: text('updated_at').notNull().default('CURRENT_TIMESTAMP'),
});
```

**索引：** `round_id` (UNIQUE)

### 9.7 agent_scores

Agent 评分结果。

```typescript
export const agentScores = sqliteTable('agent_scores', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  agent_id: text('agent_id').notNull().references(() => agents.agent_id),
  token_address: text('token_address'),

  // 总分
  score_total: real('score_total').notNull(),

  // 各维度得分
  council_probability_score: real('council_probability_score').default(0),
  trading_performance_score: real('trading_performance_score').default(0),
  rank_trend_score: real('rank_trend_score').default(0),
  token_market_score: real('token_market_score').default(0),
  visibility_score: real('visibility_score').default(0),
  risk_penalty: real('risk_penalty').default(0),

  // 标签和推荐
  label: text('label'),                        // hot_candidate | candidate | high_watch | watch | ignore | risk_alert
  recommended_action: text('recommended_action'), // watch | probe_buy | confirm_buy | hold | reduce | sell_or_exit | block_trade

  // 可解释性
  reasons: text('reasons'),                    // JSON array of reason strings
  risk_warnings: text('risk_warnings'),        // JSON array of risk warning strings

  // 元数据
  config_version: text('config_version'),      // 评分配置版本号
  scored_at: text('scored_at').notNull(),
});
```

**索引：** `(agent_id, scored_at)`, `(score_total, scored_at)`

### 9.8 trade_signals

交易信号表。

```typescript
export const tradeSignals = sqliteTable('trade_signals', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  signal_id: text('signal_id').notNull().unique(),
  agent_id: text('agent_id'),
  token_address: text('token_address').notNull(),
  symbol: text('symbol'),

  action: text('action').notNull(),            // watch | probe_buy | confirm_buy | hold | reduce | sell_or_exit | block_trade
  confidence: text('confidence').default('medium'), // low | medium | high

  // 交易参数
  max_position_usdc: real('max_position_usdc'),
  slippage_limit_pct: real('slippage_limit_pct'),
  stop_loss_pct: real('stop_loss_pct'),
  take_profit_pct: real('take_profit_pct'),
  time_exit_hours: integer('time_exit_hours'),

  // 理由
  reason: text('reason'),
  key_factors: text('key_factors'),            // JSON array

  // 风控检查结果
  risk_checks: text('risk_checks'),            // JSON object

  // 信号状态
  status: text('status').notNull().default('pending'),
  // pending | pending_approval | approved | rejected | executing | executed | failed | expired | cancelled

  // 事件窗口
  event_window: text('event_window'),

  // 标签
  label: text('label'),                        // 生成信号时的 Agent 标签

  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  expires_at: text('expires_at'),
});
```

**索引：** `signal_id` (UNIQUE), `(token_address, status)`, `(status, created_at)`

### 9.9 trade_orders

交易订单表。

```typescript
export const tradeOrders = sqliteTable('trade_orders', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  order_id: text('order_id').notNull().unique(),
  signal_id: text('signal_id').references(() => tradeSignals.signal_id),
  token_address: text('token_address').notNull(),

  action: text('action').notNull(),            // buy | sell
  amount_usdc: real('amount_usdc'),
  amount_token: real('amount_token'),

  expected_price: real('expected_price'),
  actual_price: real('actual_price'),
  slippage: real('slippage'),                  // 实际滑点

  status: text('status').notNull().default('pending'),
  // pending | approved | rejected | submitted | confirmed | failed | cancelled | closed

  tx_hash: text('tx_hash'),
  error_message: text('error_message'),

  position_id: integer('position_id'),         // 关联持仓 ID

  approved_at: text('approved_at'),
  submitted_at: text('submitted_at'),
  confirmed_at: text('confirmed_at'),
  failed_at: text('failed_at'),

  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  updated_at: text('updated_at').notNull().default('CURRENT_TIMESTAMP'),
});
```

**索引：** `order_id` (UNIQUE), `signal_id`, `tx_hash`

### 9.10 positions

持仓表。

```typescript
export const positions = sqliteTable('positions', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  token_address: text('token_address').notNull(),
  agent_id: text('agent_id'),

  // 持仓信息
  amount_token: real('amount_token'),
  cost_usdc: real('cost_usdc'),
  entry_price: real('entry_price'),

  // 当前状态
  current_price: real('current_price'),
  unrealized_pnl: real('unrealized_pnl'),       // 浮盈浮亏（USDC）
  realized_pnl: real('realized_pnl'),            // 已实现盈亏（USDC）

  // 退出条件
  stop_loss_price: real('stop_loss_price'),
  take_profit_price: real('take_profit_price'),
  time_exit_at: text('time_exit_at'),            // 时间退出 deadline

  // 状态
  status: text('status').notNull().default('open'),  // open | closing | closed

  // 关联信号
  entry_signal_id: text('entry_signal_id'),
  exit_signal_id: text('exit_signal_id'),

  // 模式
  mode: text('mode').default('paper'),           // paper | live

  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
  closed_at: text('closed_at'),
});
```

**索引：** `(token_address, status)`, `status`

### 9.11 trade_reviews

交易复盘表。

```typescript
export const tradeReviews = sqliteTable('trade_reviews', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  position_id: integer('position_id').references(() => positions.id),

  // 入场信息
  entry_reason: text('entry_reason'),
  entry_score: real('entry_score'),              // 入场时的评分
  entry_rank: integer('entry_rank'),             // 入场时的排名
  entry_liquidity: real('entry_liquidity'),       // 入场时的流动性
  entry_price: real('entry_price'),

  // 退出信息
  exit_reason: text('exit_reason'),
  exit_score: real('exit_score'),                // 退出时的评分
  exit_rank: integer('exit_rank'),               // 退出时的排名
  exit_liquidity: real('exit_liquidity'),         // 退出时的流动性
  exit_price: real('exit_price'),

  // 交易结果
  holding_minutes: integer('holding_minutes'),
  pnl_usdc: real('pnl_usdc'),
  pnl_pct: real('pnl_pct'),
  slippage: real('slippage'),

  // 失败原因分类
  mistake_type: text('mistake_type'),
  // 追高 | 流动性不足 | 事件预期失败 | AI Council 未入选 | AI Pot 表现不佳
  // 止损过窄 | 退出过早 | 数据延迟 | 执行失败 | 策略噪音

  // 复盘文本
  review_text: text('review_text'),
  llm_review: text('llm_review'),                // LLM 生成的复盘（可选）

  created_at: text('created_at').notNull().default('CURRENT_TIMESTAMP'),
});
```

**索引：** `position_id`, `mistake_type`

### 9.12 system_events

系统事件日志表。

```typescript
export const systemEvents = sqliteTable('system_events', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  time: text('time').notNull(),
  module: text('module').notNull(),              // collector | scoring | signal | risk | executor | position | review | api
  level: text('level').notNull(),                // fatal | error | warn | info | debug
  event: text('event').notNull(),
  detail: text('detail'),
  trace_id: text('trace_id'),
  metadata: text('metadata'),                    // JSON，附加数据
});
```

**索引：** `(module, time)`, `(level, time)`, `time`

### 9.13 position_snapshots

持仓快照（用于复盘分析的历史数据）。

```typescript
export const positionSnapshots = sqliteTable('position_snapshots', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  position_id: integer('position_id').notNull().references(() => positions.id),
  token_address: text('token_address').notNull(),
  price: real('price').notNull(),
  unrealized_pnl: real('unrealized_pnl'),
  snapshot_at: text('snapshot_at').notNull(),
});
```

**索引：** `(position_id, snapshot_at)`

## 表关系图

```
agents (1) ── (N) agent_snapshots
agents (1) ── (N) agent_scores
agents (1) ── (N) positions

tokens (1) ── (N) token_market_snapshots
tokens (1) ── (N) trade_signals
tokens (1) ── (N) trade_orders
tokens (1) ── (N) positions

trade_signals (1) ── (N) trade_orders
trade_orders (1) ── (1) positions
positions (1) ── (N) position_snapshots
positions (1) ── (1) trade_reviews

ai_pot_rounds (独立表)
leaderboard_snapshots (独立表)
system_events (独立表)
```

## 索引策略

| 表 | 索引 | 用途 |
|----|------|------|
| agents | agent_id UNIQUE | 查询 Agent |
| agents | token_address | Agent 与 Token 关联 |
| agent_snapshots | (agent_id, snapshot_at) | 时间范围查询 |
| agent_snapshots | (rank, snapshot_at) | 排行榜查询 |
| tokens | token_address UNIQUE | 查询 Token |
| token_market_snapshots | (token_address, snapshot_at) | 市场数据时间范围 |
| agent_scores | (agent_id, scored_at) | 评分历史 |
| agent_scores | (score_total, scored_at) | 排序查询 |
| trade_signals | signal_id UNIQUE | 信号查询 |
| trade_signals | (token_address, status) | 持仓关联 |
| trade_signals | (status, created_at) | 状态筛选 |
| trade_orders | order_id UNIQUE | 订单查询 |
| positions | (token_address, status) | 持仓查询 |
| positions | status | 开仓/平仓筛选 |
| system_events | (module, time) | 模块日志 |

## 迁移策略

### 开发阶段

```bash
# 使用 drizzle-kit push 直接同步（开发快速迭代）
npx drizzle-kit push

# 生成迁移文件
npx drizzle-kit generate

# 执行迁移
npx drizzle-kit migrate
```

### 生产阶段

```bash
# 生成迁移文件
npx drizzle-kit generate

# 审查迁移文件
# 确认无误后执行
npx drizzle-kit migrate
```

### Schema 变更流程

1. 修改 TypeScript schema 定义
2. 运行 `generate` 生成迁移文件
3. 审查迁移 SQL（关键步骤）
4. 运行 `migrate` 执行变更
5. 提交 schema 和迁移文件到 git

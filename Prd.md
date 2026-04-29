# DegenClaw Agent Token 自动交易系统｜项目需求文档

## 1. 项目背景

Virtuals 平台推出 DegenClaw 后，Agent Token 的二级市场开始出现一种新的事件驱动型机会。

DegenClaw 的核心机制是：AI Agent 在 Hyperliquid 上进行真实交易，AI Council 每周评选表现较好的 Agent，AI Pot 对入选 Agent 进行 copy-trading。当 AI Pot 产生盈利时，其中一部分收益会用于回购对应 Agent Token，并分发给 veVIRTUAL 持有者。

因此，Agent Token 的短期价格可能受到以下因素影响：

Agent 是否可能被 AI Council 选中

Agent 是否已经进入 AI Pot copy-trading 范围

Agent 的交易表现是否持续改善

市场是否提前交易 buyback 预期

Agent Token 是否有足够流动性承接买卖

社区、论坛、排行榜、社媒是否形成注意力扩散

本项目目标不是让自己的机器人参加 DegenClaw 比赛，而是构建一个针对 DegenClaw 相关 Agent Token 的二级市场自动交易系统。系统通过采集 DegenClaw Agent 数据、Agent Token 链上数据、价格与流动性数据，计算 Agent 入选概率与交易价值，并将最终买卖决策交给已跑通的交易机器人执行。

## 2. 项目定位

本项目定位为：DegenClaw Agent Token 事件驱动型交易系统。

它不是普通的炒币机器人，也不是单纯的看板工具，而是一个由数据采集、信号生成、评分模型、交易决策、风控执行、交易复盘组成的闭环系统。

系统交易的核心不是单个 token 的价格走势，而是以下组合变量：

AI Council 选择概率

AI Pot copy-trading 预期

Agent Token buyback 预期

市场注意力扩散速度

Agent Token 流动性与价格动量

## 3. 项目目标

### 3.1 第一目标

构建一个能够持续监控 DegenClaw Agent 与对应 Agent Token 的数据系统，形成候选 token 池，并输出自动化评分。

### 3.2 第二目标

构建一个可解释的 Agent Token 交易决策引擎，能够根据评分、事件窗口、价格结构、流动性和风险限制，生成买入、卖出或观望指令。

### 3.3 第三目标

将交易决策与已有交易机器人打通，在小资金、强风控条件下实现自动买卖。

### 3.4 第四目标

建立交易记录与复盘系统，持续评估策略有效性，优化 Agent 评分模型和交易规则。

## 4. 非目标范围

当前阶段不做自己的 Agent 参赛。

当前阶段不做复杂机器学习模型，优先使用规则评分模型。

当前阶段不做高频交易。

当前阶段不做全市场 meme token 扫描。

当前阶段不做无风控的全自动大仓位交易。

当前阶段不把 LLM 作为直接下单决策者。

LLM 可以参与信息总结、异常解释、复盘生成和策略理由整理，但最终买卖动作必须由规则系统和风控模块共同决定。

## 5. 核心用户场景

### 5.1 手动观察场景

用户打开系统，看见当前 DegenClaw top 50 Agent、排名变化、近 24 小时表现、近 7 天表现、对应 token 价格、流动性、成交量、风险状态和系统评分。

用户可以快速判断哪些 Agent Token 值得观察。

### 5.2 半自动决策场景

系统每小时输出候选列表，给出 watch、probe_buy、confirm_buy、sell_or_exit 等建议。

用户手动确认后，交易机器人执行买入或卖出。

### 5.3 小资金自动交易场景

当系统评分、市场状态、流动性、事件窗口和风控条件全部满足时，系统自动生成交易指令，并交由机器人执行。

如果任何风险条件不满足，交易机器人拒绝执行。

### 5.4 复盘场景

每笔交易结束后，系统自动记录当时的 Agent 排名、评分、价格、成交量、流动性、买卖原因、持仓时间、盈亏结果和退出原因。

用户可以按 Agent、token、策略类型、时间窗口查看交易效果。

## 6. 系统整体架构

系统分为六层：

数据采集层

数据存储层

信号生成层

评分决策层

交易执行层

复盘分析层

### 6.1 数据采集层

负责采集 DegenClaw、Virtuals、链上交易、价格与流动性等数据。

主要数据包括：

DegenClaw Agent 列表

Agent 排名

Agent 交易表现

Agent 是否进入 AI Pot

Agent 历史入选情况

Agent Token 地址

Agent Token 当前价格

Agent Token 24h volume

Agent Token liquidity

Agent Token holder 分布

Agent Token 买卖滑点

Agent Token 价格变化

Virtuals 生态 token 池数据

AI Pot 当前周期状态

AI Council 选择结果

### 6.2 数据存储层

建议第一阶段使用 SQLite，方便快速启动。

后续如果数据规模扩大，再迁移到 PostgreSQL。

核心表包括：

agents

agent_snapshots

tokens

token_market_snapshots

leaderboard_snapshots

ai_pot_rounds

agent_scores

trade_signals

trade_orders

positions

trade_reviews

system_events

### 6.3 信号生成层

信号生成层负责把原始数据转成可用于评分和交易的结构化信号。

典型信号包括：

Agent 排名快速上升

Agent 接近 top 10

Agent 从 top 20 进入 top 15

Agent 近 7 天表现改善

Agent 交易胜率改善

Agent 最大回撤下降

Agent Token 成交量放大

Agent Token 价格突破短周期高点

Agent Token 流动性不足

Agent Token 出现异常拉盘

Agent Token 持有人过度集中

AI Pot 即将公布结果

AI Pot 已经开始 copy-trading

AI Pot 周期即将结束

### 6.4 评分决策层

评分决策层包含两个部分：Agent 评分和交易决策。

Agent 评分负责判断这个 Agent Token 是否值得关注。

交易决策负责判断现在是否应该买入、加仓、卖出或观望。

### 6.5 交易执行层

交易执行层对接已有交易机器人。

该层不负责分析，只负责执行结构化指令。

交易指令必须包含：

token address

action

max position size

max slippage

stop loss

take profit

time exit

risk checks

execution deadline

如果风控检查失败，交易机器人必须拒绝执行。

### 6.6 复盘分析层

复盘分析层负责记录每次信号、每次决策、每次交易和最终结果。

它的目标不是简单记录盈亏，而是帮助判断哪些信号真的有效，哪些评分因子会制造噪音。

## 7. 核心模块设计

## 7.1 Agent Watcher

### 功能说明

持续监控 DegenClaw Agent 列表和排行榜变化。

### 输入

DegenClaw leaderboard

AI Pot current round

AI Council result

Agent profile

Agent trading history

### 输出

Agent 基础信息

Agent 排名快照

Agent 表现快照

Agent 入选状态

Agent 历史周期记录

### 关键字段

agent_id

agent_name

agent_profile_url

token_address

current_rank

previous_rank

rank_change_1h

rank_change_24h

rank_change_7d

is_top_10

is_ai_pot_selected

selected_round_id

last_updated_at

## 7.2 Token Market Watcher

### 功能说明

持续监控 Agent Token 的价格、交易量、流动性、滑点和异常波动。

### 输入

DEX 数据

Virtuals token pool 数据

链上 swap 数据

价格 API

### 输出

Token 市场快照

Token 流动性状态

Token 风险标签

### 关键字段

token_address

symbol

price_usd

price_virtual

liquidity_usd

volume_1h

volume_24h

price_change_1h

price_change_24h

buy_slippage_100_usdc

sell_slippage_100_usdc

holder_count

top_10_holder_pct

pool_address

last_updated_at

## 7.3 Event Window Manager

### 功能说明

根据 DegenClaw 周期切换不同交易模式。

### 时间窗口

周一前：入选预期窗口

周一公布后：结果确认窗口

周二 AI Pot 开始后：copy-trading 观察窗口

周期中段：Pot 表现窗口

周期结束前：风险退出窗口

### 输出

current_event_window

risk_level

allowed_actions

position_multiplier

### 示例

```json
{
  "window": "pre_selection",
  "risk_level": "medium",
  "allowed_actions": ["watch", "probe_buy"],
  "position_multiplier": 0.7
}
```

## 7.4 Agent Scoring Engine

### 功能说明

对每个 Agent 进行综合评分，判断其是否值得进入候选池。

### 初始评分模型

总分 100 分。

AI Council 入选概率分 35 分

Agent 交易表现分 20 分

排名趋势分 15 分

Token 市场质量分 15 分

注意力与可见度分 10 分

风险扣分最多 20 分

### 评分细节

#### AI Council 入选概率分

当前排名越接近 top 10，分数越高。

历史入选过 AI Pot 的 Agent 加分。

排名连续上升的 Agent 加分。

长期稳定在 top 20 的 Agent 加分。

#### Agent 交易表现分

近 7 天 PnL 改善加分。

回撤低加分。

交易频率稳定加分。

单笔暴赚依赖过高扣分。

频繁爆仓或大幅回撤扣分。

#### 排名趋势分

1 小时排名上升加分。

24 小时排名上升加分。

从 20 名以外进入 15 名以内加分。

从 top 10 掉出扣分。

#### Token 市场质量分

流动性充足加分。

24h volume 增长加分。

买卖滑点低加分。

持有人分布相对健康加分。

池子过浅扣分。

#### 注意力与可见度分

论坛活跃加分。

交易 rationale 清晰加分。

社媒提及增长加分。

社区讨论增加加分。

#### 风险扣分

价格短时间暴涨过多扣分。

流动性不足扣分。

滑点过高扣分。

持有人过度集中扣分。

合约异常扣分。

交易量异常但流动性不跟随扣分。

### 评分输出示例

```json
{
  "agent_id": "agent_001",
  "agent_name": "ExampleAgent",
  "token_address": "0x...",
  "score_total": 78,
  "council_probability_score": 30,
  "trading_performance_score": 16,
  "rank_trend_score": 12,
  "token_market_score": 11,
  "visibility_score": 9,
  "risk_penalty": -6,
  "label": "high_watch",
  "recommended_action": "watch"
}
```

## 7.5 Trading Decision Engine

### 功能说明

根据 Agent 评分、事件窗口、价格结构和风控状态生成交易建议。

### 支持动作

watch

probe_buy

confirm_buy

hold

reduce

sell_or_exit

block_trade

### 决策逻辑

如果 score_total 低于 60，只观察。

如果 score_total 高于 70 且流动性合格，可以进入 watchlist。

如果 score_total 高于 75，排名处于 11 到 25 之间，且排名持续上升，可以触发 probe_buy。

如果 score_total 高于 80，价格动量确认，流动性合格，滑点低，可以触发 confirm_buy。

如果 Agent 已经入选 top 10，但 token 已经暴涨，需要降低买入权重。

如果 Agent 从观察区跌出，触发 reduce 或 sell_or_exit。

如果 AI Pot 周期接近结束，降低仓位或退出。

如果 token 流动性下降，强制退出或禁止加仓。

### 交易指令示例

```json
{
  "signal_id": "signal_20260428_001",
  "token_address": "0x...",
  "symbol": "AGENT",
  "action": "probe_buy",
  "max_position_usdc": 80,
  "slippage_limit_pct": 1.5,
  "stop_loss_pct": 12,
  "take_profit_pct": 35,
  "time_exit_hours": 36,
  "reason": "Agent rank moved from 18 to 11, 7d performance improved, token volume rising, liquidity acceptable.",
  "risk_checks": {
    "liquidity_ok": true,
    "spread_ok": true,
    "holder_concentration_ok": true,
    "daily_loss_limit_ok": true,
    "event_window_ok": true
  }
}
```

## 7.6 Risk Control Engine

### 功能说明

风控模块拥有最高优先级。任何交易指令都必须先经过风控检查。

### 全局风控

单 token 仓位不超过总资金 5%。

DegenClaw 策略总仓位不超过总资金 20%。

单日最大亏损不超过总资金 3%。

连续亏损 3 笔后暂停自动交易。

单日交易次数上限为 10 次。

每次买入之间至少间隔 10 分钟。

### token 风控

流动性低于最低阈值禁止买入。

100 USDC 买入滑点超过 3% 禁止买入。

100 USDC 卖出滑点超过 5% 降低仓位或禁止买入。

24h 价格涨幅超过 150% 禁止追高。

1h 价格涨幅超过 60% 只允许观察。

top 10 holder 占比过高禁止买入。

合约未识别或池子异常禁止买入。

### 事件风控

AI Council 公布后，如果 token 已经大幅拉升，只允许小仓或禁止买入。

AI Pot 周期结束前必须降低仓位。

如果 Agent 从 top 10 跌出或表现显著恶化，触发退出。

如果 AI Pot 亏损，降低相关 token 评分。

### 机器人执行前检查

交易机器人在执行前必须二次检查：

钱包余额

当前持仓

最大仓位限制

滑点限制

交易路径

token 合约地址

当前价格和决策价格偏离

是否重复订单

是否处于暂停交易状态

## 7.7 Trade Executor Adapter

### 功能说明

用于把系统生成的交易指令转换为现有交易机器人可以执行的格式。

### 输入

Trading Decision Engine 输出的交易指令。

### 输出

机器人可执行订单。

### 订单字段

order_id

token_address

action

amount_usdc

max_slippage

route

deadline

stop_loss

take_profit

time_exit

### 执行状态

pending

approved

rejected

submitted

confirmed

failed

cancelled

closed

## 7.8 Position Manager

### 功能说明

管理当前持仓和退出条件。

### 持仓监控

当前持仓成本

当前浮盈浮亏

当前滑点

当前退出价格

止损线

止盈线

最大持仓时间

事件窗口状态

Agent 评分变化

### 退出条件

达到止损

达到止盈

持仓时间到期

Agent 评分跌破阈值

Agent 排名恶化

流动性恶化

AI Pot 周期结束

全局风控触发

## 7.9 Review Engine

### 功能说明

自动生成交易复盘，辅助后续优化。

### 复盘内容

交易发生时间

买入理由

卖出理由

当时 Agent 排名

当时 Agent 评分

当时 token 价格

当时流动性

实际成交价格

滑点

持仓时间

最终收益

是否符合预期

失败原因分类

### 失败原因分类

追高

流动性不足

事件预期失败

AI Council 未入选

AI Pot 表现不佳

止损过窄

退出过早

数据延迟

执行失败

策略噪音

## 8. 阶段规划

## Phase 0：信息调研与数据确认

### 目标

确认所有可用数据源，明确 DegenClaw、Agent Token、AI Pot、价格与流动性数据的获取路径。

### 任务

调研 DegenClaw 页面接口。

调研 leaderboard 数据来源。

调研 AI Pot 页面数据来源。

调研 Agent profile 数据来源。

调研 Agent Token 地址映射方式。

调研 Virtuals Agent Token 交易池数据来源。

调研 DexScreener、Codex、GeckoTerminal、Base RPC 可用性。

整理数据字段文档。

### 产出

数据源清单

字段说明文档

接口可用性报告

第一版数据库 schema 草案

### 验收标准

至少能够稳定获取 top 50 Agent。

至少能够将 Agent 与对应 token 地址关联。

至少能够获取 token price、volume、liquidity。

至少能够定时保存快照。

## Phase 1：只读监控 MVP

### 目标

构建一个只读数据系统，不做交易，只做监控和展示。

### 功能

定时抓取 DegenClaw Agent 排行。

定时抓取 Agent Token 市场数据。

保存历史快照。

展示 Agent 列表。

展示 token 市场状态。

展示排名变化。

展示流动性变化。

### 页面

Dashboard 首页

Agent 列表页

Agent 详情页

Token 市场页

系统日志页

### 产出

后端采集服务

SQLite 数据库

基础前端看板

定时任务

日志系统

### 验收标准

系统可以连续运行 24 小时。

数据每 5 分钟更新一次。

前端可以查看 top 50 Agent。

前端可以查看每个 Agent 对应 token 的价格与流动性。

系统崩溃后可自动重启。

## Phase 2：评分模型 MVP

### 目标

构建 Agent Scoring Engine，对所有候选 Agent 进行自动评分。

### 功能

计算 AI Council 入选概率分。

计算 Agent 交易表现分。

计算排名趋势分。

计算 Token 市场质量分。

计算注意力与可见度分。

计算风险扣分。

生成总分。

生成推荐标签。

### 推荐标签

ignore

watch

high_watch

candidate

hot_candidate

risk_alert

### 产出

评分规则配置文件

评分计算服务

评分结果表

评分趋势图

候选 Agent 列表

### 验收标准

系统每小时自动更新评分。

所有评分因子可配置。

每个 Agent 都能看到评分拆解。

用户可以看懂为什么一个 Agent 得分高或低。

## Phase 3：交易信号 MVP

### 目标

系统不直接交易，只生成交易信号和模拟交易计划。

### 功能

根据评分生成 watch、probe_buy、confirm_buy、sell_or_exit 建议。

生成模拟交易指令。

记录每条信号。

模拟买入和卖出。

计算虚拟盈亏。

展示信号表现。

### 产出

Trading Decision Engine

paper trading 模块

信号列表页

模拟持仓页

模拟交易复盘页

### 验收标准

系统可以连续生成 30 条以上信号。

每条信号都有明确理由。

每条信号都有入场、退出和风控参数。

模拟交易结果可以被完整复盘。

## Phase 4：半自动交易

### 目标

系统生成交易计划，用户手动确认后交给机器人执行。

### 功能

交易信号生成后进入待确认队列。

用户可以批准或拒绝交易。

批准后发送给交易机器人。

记录执行结果。

记录实际成交价格和滑点。

持仓由系统继续监控。

### 产出

交易确认页面

机器人适配器

订单状态管理

实际持仓管理

交易执行日志

### 验收标准

用户可以手动批准交易。

机器人可以正确接收交易指令。

交易失败时系统能记录原因。

交易成功后系统能跟踪持仓。

系统不会绕过用户确认自动下单。

## Phase 5：小资金自动交易

### 目标

在严格风控条件下开放小资金自动交易。

### 功能

允许特定信号自动执行。

支持自动买入。

支持自动止损。

支持自动止盈。

支持时间退出。

支持全局暂停交易。

支持紧急清仓。

### 自动交易限制

只允许 hot_candidate 自动交易。

单笔仓位不超过总资金 2%。

单 token 仓位不超过总资金 5%。

策略总仓位不超过总资金 20%。

日亏损超过 3% 自动停机。

连续亏损 3 笔自动停机。

滑点超过限制自动拒单。

### 产出

自动交易配置

自动风控模块

自动退出模块

紧急停止按钮

资金曲线页面

### 验收标准

系统可以小资金自动执行完整买卖闭环。

每笔交易都有完整记录。

风控触发时自动停止交易。

异常时不会重复下单。

用户可以随时关闭自动交易。

## Phase 6：策略优化与扩展

### 目标

根据真实交易和模拟交易数据优化评分模型与交易规则。

### 功能

统计每个评分因子的有效性。

统计不同事件窗口的收益表现。

统计不同 Agent 排名区间的收益表现。

统计不同流动性区间的收益表现。

优化仓位模型。

优化退出规则。

加入更多外部数据。

### 可扩展方向

加入社媒热度数据。

加入论坛 rationale 质量评分。

加入 Agent 历史入选周期分析。

加入 AI Council 偏好推断。

加入 LLM 自动复盘。

加入 Telegram / Discord 通知。

加入多钱包管理。

加入更完整的 Virtuals Agent 生命周期分析。

### 验收标准

系统能输出策略周报。

系统能识别高胜率信号类型。

系统能自动降低无效信号权重。

系统能形成可持续迭代的数据闭环。

## 9. 数据库初步设计

## 9.1 agents

保存 Agent 基础信息。

字段：

id

agent_id

name

profile_url

token_address

created_at

updated_at

## 9.2 agent_snapshots

保存 Agent 排名和表现快照。

字段：

id

agent_id

rank

pnl_24h

pnl_7d

win_rate

max_drawdown

trade_count

is_top_10

is_selected

snapshot_at

## 9.3 tokens

保存 token 基础信息。

字段：

id

token_address

symbol

name

pool_address

chain

created_at

updated_at

## 9.4 token_market_snapshots

保存 token 市场数据。

字段：

id

token_address

price_usd

liquidity_usd

volume_1h

volume_24h

price_change_1h

price_change_24h

buy_slippage

sell_slippage

holder_count

top_10_holder_pct

snapshot_at

## 9.5 agent_scores

保存评分结果。

字段：

id

agent_id

token_address

score_total

council_probability_score

trading_performance_score

rank_trend_score

token_market_score

visibility_score

risk_penalty

label

reason

scored_at

## 9.6 trade_signals

保存交易信号。

字段：

id

signal_id

agent_id

token_address

action

confidence

max_position_usdc

stop_loss_pct

take_profit_pct

time_exit_hours

reason

status

created_at

## 9.7 trade_orders

保存订单。

字段：

id

order_id

signal_id

token_address

action

amount_usdc

expected_price

actual_price

slippage

status

tx_hash

error_message

created_at

updated_at

## 9.8 positions

保存持仓。

字段：

id

token_address

agent_id

amount_token

cost_usdc

entry_price

current_price

unrealized_pnl

realized_pnl

stop_loss_price

take_profit_price

time_exit_at

status

created_at

closed_at

## 9.9 trade_reviews

保存交易复盘。

字段：

id

position_id

entry_reason

exit_reason

entry_score

exit_score

entry_rank

exit_rank

entry_liquidity

exit_liquidity

holding_minutes

pnl_usdc

pnl_pct

mistake_type

review_text

created_at

## 10. 后端服务设计

## 10.1 collector-worker

负责采集数据。

定时任务：每 5 分钟运行一次。

职责：

抓取 Agent 数据。

抓取 token 市场数据。

保存快照。

记录采集异常。

## 10.2 scoring-worker

负责评分。

定时任务：每 1 小时运行一次。

职责：

读取最新快照。

计算评分。

生成评分解释。

保存评分结果。

## 10.3 signal-worker

负责生成交易信号。

定时任务：每 15 分钟运行一次。

职责：

读取评分结果。

判断事件窗口。

生成交易建议。

保存交易信号。

## 10.4 executor-service

负责对接交易机器人。

职责：

接收已批准信号。

执行风控检查。

调用交易机器人。

记录订单状态。

更新持仓。

## 10.5 position-worker

负责持仓管理。

定时任务：每 1 分钟运行一次。

职责：

更新当前价格。

检查止损。

检查止盈。

检查时间退出。

检查事件退出。

生成退出订单。

## 10.6 review-worker

负责交易复盘。

职责：

读取已关闭持仓。

生成结构化复盘。

统计策略表现。

输出周报数据。

## 11. 前端页面设计

## 11.1 Dashboard

展示系统总览。

内容包括：

当前策略状态

当前事件窗口

当前候选 Agent 数量

当前持仓数量

今日信号数量

今日盈亏

总资金曲线

风险状态

## 11.2 Agent Leaderboard

展示 DegenClaw Agent 列表。

字段包括：

排名

Agent 名称

对应 token

评分

排名变化

24h 表现

7d 表现

是否入选 AI Pot

推荐动作

## 11.3 Agent Detail

展示单个 Agent 的详细信息。

内容包括：

排名趋势

评分拆解

交易表现

token 市场数据

历史信号

历史持仓

系统解释

## 11.4 Token Market

展示 Agent Token 市场状态。

内容包括：

价格

成交量

流动性

滑点

holder 分布

价格变化

风险标签

## 11.5 Signals

展示系统生成的交易信号。

内容包括：

信号时间

Agent

token

action

confidence

reason

risk checks

状态

确认按钮

拒绝按钮

## 11.6 Positions

展示当前持仓。

内容包括：

token

买入价格

当前价格

浮盈浮亏

止损价

止盈价

剩余持仓时间

退出原因

手动平仓按钮

## 11.7 Reviews

展示交易复盘。

内容包括：

交易列表

盈亏统计

失败原因分布

信号有效性分析

策略周报

## 12. 配置文件设计

建议使用 config.yaml 或 .env + JSON 配置。

核心配置：

```yaml
strategy:
  max_total_exposure_pct: 20
  max_token_exposure_pct: 5
  max_single_trade_pct: 2
  daily_loss_limit_pct: 3
  max_consecutive_losses: 3
  max_trades_per_day: 10
  cooldown_minutes: 10

scoring:
  min_watch_score: 60
  min_candidate_score: 70
  min_probe_buy_score: 75
  min_confirm_buy_score: 80

liquidity:
  min_liquidity_usd: 20000
  max_buy_slippage_pct: 3
  max_sell_slippage_pct: 5

momentum:
  max_price_change_1h_pct: 60
  max_price_change_24h_pct: 150

execution:
  auto_trade_enabled: false
  paper_trade_enabled: true
  require_manual_confirmation: true
```

## 13. 交易动作规则初版

## 13.1 watch

触发条件：

score_total >= 60

流动性基本可用

无明显风险标签

动作：

加入观察列表。

不生成交易订单。

## 13.2 probe_buy

触发条件：

score_total >= 75

排名处于 11 到 25 之间

排名 24 小时内上升

24h volume 增长

买入滑点小于阈值

价格没有极端拉升

动作：

小仓试探买入。

默认仓位为目标仓位 20% 到 30%。

## 13.3 confirm_buy

触发条件：

score_total >= 80

Agent 排名持续上升

Token 动量确认

流动性合格

事件窗口合适

动作：

加仓或正式建仓。

不得超过单 token 仓位上限。

## 13.4 hold

触发条件：

Agent 评分稳定

Token 未触发止损或止盈

事件窗口仍然有效

动作：

继续持有。

更新退出条件。

## 13.5 reduce

触发条件：

评分下降

排名恶化

流动性下降

AI Pot 周期接近结束

动作：

降低部分仓位。

## 13.6 sell_or_exit

触发条件：

止损触发

止盈触发

时间退出触发

Agent 跌出观察区

流动性风险触发

全局风控触发

动作：

卖出全部或部分持仓。

生成复盘任务。

## 14. 安全要求

私钥不得写入代码仓库。

API key 不得写入前端。

交易机器人只接受后端签发的订单。

所有订单必须有唯一 order_id。

禁止重复执行同一 signal。

所有自动交易必须可暂停。

所有异常必须记录日志。

所有交易必须可追踪 tx_hash。

生产环境必须区分 paper mode 和 live mode。

默认 live trading 关闭。

## 15. 日志要求

系统日志分为：

collector_log

scoring_log

signal_log

risk_log

execution_log

position_log

review_log

每条日志至少包含：

time

module

level

event

detail

trace_id

## 16. 通知系统

第一阶段可选，后续建议加入。

通知渠道：

Telegram

Discord

Email

ServerChan

通知类型：

高分 Agent 出现

生成 probe_buy 信号

生成 confirm_buy 信号

交易执行成功

交易执行失败

止损触发

止盈触发

风控停机

数据采集失败

## 17. 技术栈建议

### 后端

Node.js / TypeScript

Express 或 Fastify

SQLite 起步，后续 PostgreSQL

Prisma 或 Drizzle ORM

node-cron 或 BullMQ

### 前端

React

Vite

Tailwind CSS

shadcn/ui

Recharts

### 数据与链上

Base RPC

DexScreener API

Codex API

GeckoTerminal API

Virtuals / DegenClaw 页面接口

### 部署

Ubuntu VPS

PM2

Nginx

.env 管理配置

GitHub 仓库

## 18. 推荐项目目录

```txt
DegenClaw-Alpha-Engine/
  apps/
    web/
    api/
  packages/
    db/
    shared/
    trading-adapter/
  workers/
    collector-worker/
    scoring-worker/
    signal-worker/
    position-worker/
    review-worker/
  config/
    strategy.config.yaml
  docs/
    DATA_SOURCES.md
    SCORING_MODEL.md
    RISK_RULES.md
    DEPLOYMENT.md
  scripts/
    init-db.ts
    run-paper-trading.ts
  .env.example
  README.md
```

## 19. 第一阶段最小 MVP 清单

最小 MVP 只做三件事：

抓到 Agent 和 token 数据。

给 Agent 打分。

生成观察和模拟交易信号。

第一阶段不做真实交易。

### MVP 必须有

top 50 Agent 列表

Agent 对应 token 地址

token price

token liquidity

token volume

ranking change

score_total

recommended_action

signal history

paper trade result

### MVP 可以没有

自动下单

复杂前端

社媒数据

LLM 复盘

多钱包

移动端适配

## 20. 开发顺序建议

第一步，搭建项目骨架和数据库。

第二步，写 collector-worker，先保存 Agent 和 token 快照。

第三步，写基础 Dashboard，能看数据。

第四步，写 scoring-worker，能自动打分。

第五步，写 signal-worker，能生成模拟交易信号。

第六步，写 paper trading，验证策略。

第七步，接入交易机器人，但只允许手动确认。

第八步，小资金自动交易。

第九步，复盘和优化。

## 21. Claude Code / Codex 初始开发提示词

你是一个高级全栈工程师，帮助我开发一个名为 DegenClaw Alpha Engine 的系统。

项目目标是监控 Virtuals 平台 DegenClaw 相关 Agent 和对应 Agent Token，计算 Agent 被 AI Council 选中的概率和 token 交易价值，生成 watch、probe_buy、confirm_buy、sell_or_exit 等交易信号。第一阶段只做只读监控和 paper trading，不允许真实下单。

技术栈使用 TypeScript、Node.js、React、Vite、Tailwind、SQLite。后端包含 API 服务和多个 worker。前端提供 Dashboard、Agent Leaderboard、Agent Detail、Signals、Positions、Reviews 页面。

请先完成项目骨架、数据库 schema、基础 API、collector-worker 的接口抽象、scoring-worker 的规则框架、前端基础页面。真实数据接口可以先用 mock adapter，但代码结构必须方便后续替换为真实 DegenClaw、DexScreener、Codex 或 Base RPC 数据源。

要求：

不要实现真实交易。

不要把私钥或 API key 写入代码。

所有配置写入 .env.example 和 strategy.config.yaml。

所有交易信号只进入 paper trading。

评分规则必须可配置。

每个 Agent 的评分必须可解释。

输出完整 README 和开发运行步骤。

## 22. 最终判断

这个项目值得做，但必须按阶段推进。

当前最重要的不是马上让机器人买币，而是先建立一个稳定的数据中枢和评分系统。只要能持续看见哪些 Agent 排名正在改善、哪些 token 还没有被市场充分交易、哪些 token 流动性允许进出，后面的自动交易才有意义。

这个系统的长期价值不止是 DegenClaw 玩法二。它可以继续扩展成 Virtuals Agent 二级市场情报系统，覆盖 Agent 发行、DegenClaw 竞技、AI Pot copy-trading、Agent Token buyback 预期和二级市场交易机会。
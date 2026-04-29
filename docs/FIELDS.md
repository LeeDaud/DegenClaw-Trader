# 字段说明文档

> 基于 Virtuals API (api2.virtuals.io) 返回数据 + DegenClaw 业务需求定义。

---

## Agent 对象

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| id | integer | ✅ | Virtuals API | Agent 唯一 ID |
| uid | string | ✅ | Virtuals API | UUID 标识 |
| name | string | ✅ | Virtuals API | Agent 名称 |
| symbol | string | ✅ | Virtuals API | 交易代币符号 |
| description | string | | Virtuals API | Agent 描述 |
| status | string | ✅ | Virtuals API | 状态: UNDERGRAD / ACTIVE / LAUNCHED / TRADING |
| category | string | | Virtuals API | 分类: IP MIRROR / GAME / etc. |
| chain | string | ✅ | Virtuals API | 链: BASE |
| level | integer | | Virtuals API | 等级 |
| factory | string | | Virtuals API | 工厂合约类型: BONDING_V5 |
| createdAt | datetime | ✅ | Virtuals API | 创建时间 |
| launchedAt | datetime | | Virtuals API | 发射时间 |
| creator | object | | Virtuals API | 创建者信息 |
| image | object | | Virtuals API | Agent 图片 |
| cores | array | | Virtuals API | AI 核心配置 |
| acpAgentId | integer | | Virtuals API | ACP Agent ID（launched 后有值） |
| v3AcpAgentId | integer | | Virtuals API | V3 ACP Agent ID（launched 后有值） |

## Token 对象

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| tokenAddress | string | | Virtuals API | 正式 Token 合约地址（launched 后非空） |
| preToken | string | | Virtuals API | 预售 Token 地址（launch 前使用） |
| preTokenPair | string | | Virtuals API | 预售配对池地址 |
| lpAddress | string | | Virtuals API | 流动性池地址（launched 后非空） |
| totalSupply | integer | ✅ | Virtuals API | 总供应量（固定 1,000,000,000） |
| symbol | string | ✅ | Virtuals API | 代币符号 |
| virtualTokenValue | string | | Virtuals API | Virtual 计价代币值 |

## Market Snapshot 对象

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| liquidityUsd | float | ✅ | Virtuals API | USD 流动性（bonding curve 或 LP） |
| volume24h | float | ✅ | Virtuals API | 24h 成交量（USD） |
| netVolume24h | float | | Virtuals API | 24h 净成交量 |
| priceChangePercent24h | float | | Virtuals API | 24h 价格变化百分比 |
| mcapInVirtual | float | | Virtuals API | Virtual 计价市值 |
| fdvInVirtual | float | | Virtuals API | Virtual 计价完全稀释市值 |
| totalValueLocked | string | | Virtuals API | TVL |
| holderCount | integer | ✅ | Virtuals API | 持有人数量 |
| top10HolderPercentage | float | | Virtuals API | Top 10 持有人占比 |
| holderCountPercent24h | float | | Virtuals API | 24h 持有人数量变化 |
| devHoldingPercentage | float | | Virtuals API | 开发者持有占比 |
| valueFx | float | | Virtuals API | 价值因子 |
| hasMarginTrading | bool | | Virtuals API | 是否支持杠杆交易 |

## 交易信号对象（信号生成阶段定义）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| signal_id | string | ✅ | 格式: `signal_YYYYMMDD_HHMMSS_XXX` |
| agent_id | integer | ✅ | 关联 Agent ID |
| token_address | string | ✅ | Token 合约地址 |
| action | string | ✅ | probe_buy / confirm_buy / hold / reduce / sell_or_exit |
| score | float | ✅ | 综合评分 (0-100) |
| score_breakdown | json | ✅ | 各维度评分拆解 |
| position_size_usd | float | ✅ | 建议仓位 (USD) |
| stop_loss_pct | float | ✅ | 止损百分比 |
| take_profit_pct | float | ✅ | 止盈百分比 |
| time_exit_hours | float | ✅ | 持仓时间上限（小时） |
| event_window | string | ✅ | 触发时的事件窗口 |
| reason | string | ✅ | 信号理由 |
| risk_warnings | json | | 风险警告列表 |
| status | string | ✅ | 状态: pending / approved / rejected / executed / expired |
| created_at | datetime | ✅ | 创建时间 |
| expired_at | datetime | | 过期时间（超时未确认） |

## 评分结果对象（评分引擎输出）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_id | integer | ✅ | Agent ID |
| score_total | integer | ✅ | 综合评分 (0-100) |
| council_probability_score | integer | ✅ | AI Council 入选概率 (0-35) |
| rank_to_score | integer | | 排名接近 top 10 (0-15) |
| history_selection_bonus | integer | | 历史入选加分 (0-10) |
| rank_momentum_bonus | integer | | 排名连续上升 (0-5) |
| top20_stability_bonus | integer | | 长期稳定 top 20 (0-5) |
| trading_performance_score | integer | ✅ | 交易表现 (0-20) |
| pnl_improvement | integer | | 7d PnL 改善 (0-8) |
| drawdown_score | integer | | 回撤评分 (0-4) |
| trade_frequency_stability | integer | | 交易频率稳定性 (0-4) |
| single_trade_dependency_penalty | integer | | 单笔暴赚扣分 (-4-0) |
| rank_trend_score | integer | ✅ | 排名趋势 (0-15) |
| rank_change_1h | integer | | 1h 排名变化 (0-5) |
| rank_change_24h | integer | | 24h 排名变化 (0-5) |
| threshold_breakthrough | integer | | 阈值突破 (0-3) |
| top10_drop_penalty | integer | | 跌出 top 10 (-2-0) |
| token_market_score | integer | ✅ | 市场质量 (0-15) |
| liquidity_score | integer | | 流动性 (0-5) |
| volume_growth | integer | | 成交量增长 (0-4) |
| slippage_score | integer | | 滑点 (0-3) |
| holder_distribution | integer | | 持有人分布 (0-3) |
| attention_score | integer | ✅ | 注意力与可见度 (0-10) |
| risk_penalty | integer | ✅ | 风险扣分 (0-20) |
| label | string | ✅ | hot_candidate / candidate / high_watch / watch / ignore / risk_alert |
| recommended_action | string | ✅ | 推荐操作 |
| reasons | json | ✅ | 评分理由列表 |
| risk_warnings | json | | 风险警告列表 |
| created_at | datetime | ✅ | 评分时间 |

## AI Council Result 对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| round_id | integer | ✅ | Round 编号 |
| selected_agent_ids | array | ✅ | 选中 Agent ID 列表 |
| announcement_time | datetime | ✅ | 公布时间（周一） |
| round_start | datetime | ✅ | Round 开始时间 |
| round_end | datetime | ✅ | Round 结束时间 |
| pot_pnl | float | | AI Pot 盈亏 |
| created_at | datetime | ✅ | 记录时间 |

## 交易订单对象（执行层）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_id | string | ✅ | 格式: `ord_YYYYMMDD_HHMMSS_XXX` |
| signal_id | string | ✅ | 关联信号 ID |
| agent_id | integer | ✅ | Agent ID |
| token_address | string | ✅ | Token 合约地址 |
| side | string | ✅ | buy / sell |
| amount_usd | float | ✅ | 订单金额 (USD) |
| status | string | ✅ | pending / submitted / confirmed / closed / failed |
| tx_hash | string | | 交易哈希 |
| entry_price | float | | 成交价格 |
| slippage | float | | 实际滑点 |
| gas_fee | float | | Gas 费用 |
| created_at | datetime | ✅ | 创建时间 |
| executed_at | datetime | | 执行时间 |

## 持仓对象

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| position_id | string | ✅ | 持仓 ID |
| agent_id | integer | ✅ | Agent ID |
| token_address | string | ✅ | Token 合约地址 |
| order_id | string | ✅ | 关联订单 ID |
| entry_price | float | ✅ | 买入价格 |
| amount | float | ✅ | 持仓数量 |
| current_price | float | ✅ | 当前价格（定时更新） |
| unrealized_pnl | float | ✅ | 未实现盈亏 |
| stop_loss | float | ✅ | 止损价格 |
| take_profit | float | ✅ | 止盈价格 |
| time_exit_at | datetime | ✅ | 强制退出时间 |
| status | string | ✅ | open / closed / liquidated |
| entered_at | datetime | ✅ | 开仓时间 |
| closed_at | datetime | | 平仓时间 |

# Phase 2: 评分模型 MVP — 执行清单

> 状态：✅ 已完成
> 完成日期：2026-04-29

## 1. 评分引擎框架搭建

- [x] 创建 `scoring/engine.py`
- [x] 实现 DegenClawScoreEngine 类
- [x] 实现评分结果输出（AgentScore dataclass）

## 2. AI Council 入选概率评分 (0-35 分)

- [x] 实现 rank_to_score() — 排名接近 top 10 评分（0-15）
- [x] 实现 history_selection_bonus() — 历史入选加分（0-10）
- [x] 实现 rank_momentum_bonus() — 排名连续上升加分（0-5）
- [x] 实现 top20_stability_bonus() — 长期稳定 top 20 加分（0-5）
- [x] 整合为 council_probability_score

## 3. Agent 交易表现评分 (0-20 分)

- [x] 实现 pnl_improvement() — 7d PnL 改善评分（0-8）
- [x] 实现 drawdown_score() — 回撤评分（0-4）
- [x] 实现 trade_frequency_stability() — 交易频率稳定性（0-4）
- [ ] 实现 single_trade_dependency_penalty() — 单笔暴赚扣分（-4-0）*
- [x] 整合为 trading_performance_score

## 4. 排名趋势评分 (0-15 分)

- [x] 实现 rank_change_1h() — 1 小时排名上升（0-5）
- [x] 实现 rank_change_24h() — 24 小时排名上升（0-5）
- [x] 实现 threshold_breakthrough() — 阈值突破加分（0-3）
- [x] 实现 top10_drop_penalty() — 跌出 top 10 扣分（0-2）
- [x] 整合为 rank_trend_score

## 5. Token 市场质量评分 (0-15 分)

- [x] 实现 liquidity_score() — 流动性评分（0-5）
- [x] 实现 volume_growth() — 24h 成交量增长（0-4）
- [x] 实现 slippage_score() — 滑点评分（0-3）
- [x] 实现 holder_distribution() — 持有人分布（0-3）
- [x] 整合为 token_market_score

## 6. 注意力与可见度评分 (0-10 分)

- [x] 实现基础分逻辑（Phase 2 使用合理默认值）
- [x] 预留社媒数据接入点

## 7. 风险扣分 (0-20 分)

- [x] 实现 price_spike_penalty() — 价格暴涨扣分（0-5）
- [x] 实现 low_liquidity_penalty() — 流动性不足扣分（0-4）
- [x] 实现 high_slippage_penalty() — 滑点过高扣分（0-3）
- [x] 实现 holder_concentration_penalty() — 持有人集中扣分（0-3）
- [x] 实现 volume_anomaly_penalty() — 交易量异常扣分（0-3）
- [ ] 实现 contract_anomaly_penalty() — 合约异常扣分（0-2）*

## 8. 标签与推荐逻辑

- [x] 实现 label generation（hot_candidate / candidate / high_watch / watch / ignore / risk_alert）
- [x] 实现 grade 计算（A/B/C/D/E/F）
- [ ] 实现 recommended_action 映射 *
- [ ] 实现 reasons 和 risk_warnings 文本生成 *

## 9. 评分配置

- [ ] 创建 `config/scoring.yaml` 配置文件 *
- [ ] 配置各维度权重
- [ ] 配置评分阈值参数（排名、流动性、滑点等）
- [ ] 配置风控参数（价格异常阈值、持有人集中度等）

## 10. 数据库适配

- [x] 创建 `agent_scores` 表（含评分拆解字段）
- [x] 实现 insert_agent_score() / list_agent_scores() / get_agent_score_history()

## 11. 定时评分

- [x] 配置 APScheduler 评分任务（随采集管道运行，每 5 分钟）
- [x] 实现批量评分流程（读取数据 → 计算 → 保存）
- [x] 实现数据缺失降级处理（空快照/空市场数据返回 0）

## 12. 前端更新

- [ ] Agent Leaderboard 增加评分列（score_total + 标签）*
- [ ] Agent Detail 增加评分拆解（各维度柱状图 + 雷达图）*
- [ ] 评分趋势图（time series chart）*
- [ ] Agent 列表支持按评分排序（默认降序）*

## 验收标准

- [x] 系统可以定时自动更新评分
- [ ] 所有评分因子可通过配置文件调整 *
- [x] 每个 Agent 都能看到完整的评分拆解（API 返回各维度分数）
- [x] 评分记录完整保存在 agent_scores 表
- [x] 当某维度数据缺失时，评分能优雅降级

> 注：带 * 项为可选的完善项，不影响核心功能

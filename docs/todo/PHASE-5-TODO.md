# Phase 5: 小资金自动交易 — 执行清单

> 预估工期：7-10 天
> 复用来源：OKX-Robot (015) — risk/guard, risk/take_profit

## 1. Risk Control Engine（复用 OKX-Robot guard）

- [ ] 创建 `risk/engine.py`
- [ ] 导入 DailyLossGuard（来自 OKX-Robot）
- [ ] 导入 TakeProfitMonitor（来自 OKX-Robot）
- [ ] 实现 DegenClawRiskEngine 组合风控

## 2. 全局风控

- [ ] 实现日亏损检查（复用 DailyLossGuard）
- [ ] 实现连续亏损检查（最近 3 笔交易 PnL 全负则停机）
- [ ] 实现交易频率检查（单日 ≤ 10 笔）
- [ ] 实现交易间隔检查（买入间隔 ≥ 10 分钟）
- [ ] 实现总敞口检查（≤ 总资金 20%）

## 3. Token 风控

- [ ] 实现流动性阈值检查（≥ 最低阈值）
- [ ] 实现买入滑点检查（100 USDC 买入滑点 ≤ 3%）
- [ ] 实现卖出滑点检查（100 USDC 卖出滑点 ≤ 5%）
- [ ] 实现 24h 涨幅检查（涨幅 > 150% 禁止追高）
- [ ] 实现 1h 涨幅检查（涨幅 > 60% 只允许观察）
- [ ] 实现持有人集中度检查（top 10 holder > 50% 禁止买入）

## 4. 事件风控

- [ ] 实现 AI Council 公布后价格检查
- [ ] 实现 AI Pot 周期结束前强制减仓
- [ ] 实现 Agent 跌出 top 10 触发退出
- [ ] 实现 AI Pot 亏损时降低评分

## 5. 自动执行流程

- [ ] 实现 can_auto_execute() 条件检查（标签、频率、冷却时间）
- [ ] 实现风控通过后自动提交执行
- [ ] 实现风控拒绝时详细记录原因
- [ ] 实现自动买入执行（仅限 hot_candidate）

## 6. 自动退出（复用 OKX-Robot TakeProfitMonitor）

- [ ] 集成 TakeProfitMonitor 到 position manager
- [ ] 实现止损自动卖出（价格条件触发）
- [ ] 实现止盈自动卖出（ROI 条件触发，复用 OKX-Robot）
- [ ] 实现时间自动退出（持仓超时）
- [ ] 实现评分下降自动退出（Agent 评分 < 60）
- [ ] 实现排名恶化自动退出（排名 > 30）
- [ ] 实现流动性恶化自动退出（liquidity < 20K）

## 7. 自动停机机制

- [ ] 实现日亏损超限自动停机（午夜自动恢复）
- [ ] 实现连续亏损自动停机（需手动恢复）
- [ ] 实现停机状态持久化（重启后保持停机状态）
- [ ] 实现自动恢复时间计算

## 8. 紧急停止

- [ ] 实现 `POST /api/v1/emergency/stop` — 紧急停止自动交易
- [ ] 实现 `POST /api/v1/emergency/stop?liquidate=true` — 紧急停止 + 清仓
- [ ] 实现 `POST /api/v1/emergency/resume` — 恢复自动交易
- [ ] 实现清仓时使用紧急滑点（高于正常滑点）

## 9. 新增 API

- [ ] `POST /api/v1/executor/start-auto` — 开启自动交易
- [ ] `POST /api/v1/executor/stop-auto` — 关闭自动交易
- [ ] `GET /api/v1/trading-status` — 当前交易状态
- [ ] `GET /api/v1/risk/global` — 全局风控状态
- [ ] `GET /api/v1/risk/token/:address` — Token 风控状态
- [ ] `GET /api/v1/capital/curve` — 资金曲线数据
- [ ] `GET /api/v1/capital/summary` — 资金总览

## 10. 前端更新

- [ ] 风控状态 Dashboard（全局/Token/事件风控状态）
- [ ] 资金曲线页面（净值图、回撤指标）
- [ ] 自动交易开关按钮
- [ ] 紧急停止按钮（可附带清仓选项）
- [ ] 风控触发日志展示

## 11. 配置

- [ ] 配置 auto_trading 模块（allowed_labels, 仓位限制, 亏损限制）
- [ ] 配置每日最大交易次数和冷却时间
- [ ] 配置恢复策略（日亏损次日恢复 / 连续亏损手动恢复）
- [ ] 配置紧急清仓参数

## 验收标准

- [ ] 系统可以小资金自动执行完整买卖闭环
- [ ] 每笔交易都有完整记录（信号 → 风控 → 订单 → 持仓 → 退出）
- [ ] 风控触发时自动停止交易
- [ ] 异常时不会重复下单
- [ ] 用户可以随时关闭自动交易
- [ ] 紧急停止功能正常工作
- [ ] 日亏损超限自动停机
- [ ] 连续亏损自动停机
- [ ] 自动止损/止盈/时间退出正确执行
- [ ] 资金曲线和风控状态页面数据准确

# Phase 4: 半自动交易 — 执行清单

> 预估工期：7-10 天
> 复用来源：OKX-Robot (015) — executor/okx_client, executor/trader, db/database

## 1. 交易审批流程

- [ ] 扩展 signal 状态机（新增 pending_approval / approved / rejected / executing 状态）
- [ ] 实现信号过期机制（超时未确认自动 expired）
- [ ] 实现信号审批 API（`POST /signals/:id/approve`）
- [ ] 实现信号拒绝 API（`POST /signals/:id/reject`）
- [ ] 实现信号撤销 API（用户可取消待处理信号）

## 2. 执行层 — 复用 OKX-Robot

- [ ] 创建 `executor/service.py`
- [ ] 导入 OKXDexClient（来自 OKX-Robot）
- [ ] 导入 Trader（来自 OKX-Robot）
- [ ] 实现 DegenClawExecutor 初始化（配置 client/trader）
- [ ] 实现 execute_buy() — 买入执行（委托 OKX-Robot）
- [ ] 实现 execute_sell() — 卖出执行（委托 OKX-Robot）
- [ ] 实现 get_balance() — 查询 USDC 余额
- [ ] 实现 paper/live mode 切换

## 3. 二次风控检查

- [ ] 实现当前价格偏离检查（与决策时价格对比 ≤ 5%）
- [ ] 实现流动性重新检查（数据可能已变化）
- [ ] 实现钱包余额检查
- [ ] 实现单 token 敞口检查（≤ 总资金 5%）
- [ ] 实现总敞口检查（≤ 总资金 20%）
- [ ] 实现重复订单检查（相同 signal 不可重复执行）

## 4. 订单管理

- [ ] 创建 `trade_orders` 表（复用 OKX-Robot copy_trades 表模式）
- [ ] 实现 order_id 生成（`ord_YYYYMMDD_HHMMSS_XXX`）
- [ ] 实现订单状态管理（pending → submitted → confirmed → closed）
- [ ] 实现订单执行记录（tx_hash、成交价格、滑点）

## 5. 持仓管理（真实持仓）

- [ ] 创建 `positions` 表（复用 OKX-Robot 持仓模式）
- [ ] 实现 position 创建（买入成交后自动建立）
- [ ] 实现 position 价格更新（每 1 分钟更新 current_price）
- [ ] 实现未实现盈亏计算
- [ ] 实现止损/止盈/时间退出条件保存

## 6. Position Worker

- [ ] 创建 `position/manager.py`
- [ ] 实现每 1 分钟的持仓扫描循环
- [ ] 实现止损检查触发器
- [ ] 实现止盈检查触发器
- [ ] 实现时间退出检查触发器
- [ ] 实现触发退出时生成卖出信号（需用户确认）

## 7. 订单执行日志

- [ ] 实现 execution_log 分类日志
- [ ] 记录每次执行尝试（含失败原因）
- [ ] 记录风控拒绝原因

## 8. 新增 API

- [ ] `GET /api/v1/signals/pending` — 待确认信号列表
- [ ] `GET /api/v1/orders` — 订单列表
- [ ] `GET /api/v1/orders/:id` — 订单详情
- [ ] `GET /api/v1/positions` — 当前持仓列表
- [ ] `GET /api/v1/positions/:id` — 持仓详情
- [ ] `POST /api/v1/positions/:id/close` — 手动平仓
- [ ] `GET /api/v1/executor/status` — 执行器状态
- [ ] `POST /api/v1/executor/switch-mode` — 切换 paper/live

## 9. 前端更新

- [ ] Signals 页面增加确认/拒绝按钮
- [ ] 待确认信号高亮展示
- [ ] Positions 页面显示真实持仓列表
- [ ] 持仓详情页面（成本、当前价格、浮盈浮亏、退出条件）
- [ ] 手动平仓按钮

## 10. 环境与配置

- [ ] 配置 OKX API Key/Secret/Passphrase（从 .env 读取）
- [ ] 配置交易钱包私钥和地址
- [ ] 配置 execution mode（默认 paper）
- [ ] 配置 live mode 手动开启验证

## 验收标准

- [ ] 用户可以手动批准交易
- [ ] 用户可以手动拒绝交易
- [ ] 机器人可以正确接收交易指令
- [ ] 交易失败时系统能记录原因
- [ ] 交易成功后系统能跟踪持仓
- [ ] 系统不会绕过用户确认自动下单
- [ ] 二次风控检查拦截不符合条件的交易
- [ ] 订单状态转换完全正确
- [ ] 持仓数据随价格变化实时更新
- [ ] 止损/止盈/时间退出能正确触发卖出信号

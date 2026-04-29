# Phase 3: 交易信号 MVP — 执行清单

> 状态：✅ 已完成
> 完成日期：2026-04-29

## 1. Event Window Manager

- [x] 创建 `decision/event_window.py`
- [x] 实现 5 种事件窗口定义（pre_selection / result_confirmation / copy_trading / pot_performance / risk_exit）
- [x] 实现窗口切换逻辑（基于当前日期 + AI Pot round 数据）
- [x] 实现 `get_current_window()` 方法
- [x] 实现风险等级和仓位乘数计算
- [x] 实现 allowed_actions 白名单
- [x] 参考 SignalHub `lifecycle_engine.py` 的不可逆阶段推进模式

## 2. Trading Decision Engine

- [x] 创建 `decision/engine.py`
- [x] 实现 `decide()` 主方法（输入评分结果 + 市场数据 → 输出交易动作）
- [x] 实现 probe_buy 触发条件判断（score >= 75, rank 11-25, 排名上升, vol 增长, 滑点合格）
- [x] 实现 confirm_buy 触发条件判断（score >= 80, 排名持续上升, 动量确认, 流动性合格）
- [x] 实现 hold 条件判断（评分稳定, 未触发退出条件）
- [x] 实现 reduce 条件判断（评分下降, 排名恶化, 流动性下降）
- [x] 实现 sell_or_exit 条件判断（止损/止盈/时间退出/跌出观察区）
- [x] 实现 watch/block_trade 默认逻辑

## 3. 交易参数计算

- [x] 实现仓位大小计算（`calculate_position()`）
- [x] 实现止损百分比计算（`calculate_stop_loss()`）
- [x] 实现止盈百分比计算（`calculate_take_profit()`）
- [x] 实现持仓时间计算（`calculate_time_exit()`）
- [x] 实现事件窗口仓位乘数调整

## 4. 信号去重

- [x] 实现 signal dedup（同一 token 同一动作 30 分钟内不重复）
- [x] 实现 signal_id 生成（`signal_YYYYMMDD_HHMMSS_XXX`）

## 5. Paper Trading 模块

- [x] 创建 `signal/papertrader.py`
- [x] 实现 paper position 创建（模拟买入价格和滑点）
- [x] 实现 paper position 平仓（模拟卖出和盈亏计算）
- [x] 实现模拟滑点计算（基于市场数据 + 随机因子）
- [x] 实现 paper trading 总体绩效统计
- [x] 实现 `get_paper_performance()` 接口

## 6. 数据库适配

- [x] 创建 `trade_signals` 表
- [x] 创建 `ai_pot_rounds` 补充字段（如需要）
- [x] 实现 save_signal() / get_signals() / get_signal_by_id()
- [x] 实现 paper position 存储

## 7. 定时信号生成

- [x] 配置 APScheduler 每 15 分钟信号生成任务
- [x] 实现信号生成流水线（读取评分 → 事件窗口 → 决策引擎 → 保存信号 → paper trade）
- [x] 实现 paper position 价格更新

## 8. 新增 API

- [x] 实现 `GET /api/v1/signals` — 信号列表
- [x] 实现 `GET /api/v1/signals/:id` — 信号详情
- [x] 实现 `GET /api/v1/positions/paper` — paper 持仓列表
- [x] 实现 `GET /api/v1/positions/paper/:id` — paper 持仓详情
- [x] 实现 `GET /api/v1/event-window` — 当前事件窗口
- [x] 实现 `GET /api/v1/performance/paper` — paper 表现总览

## 9. 前端新增页面

- [x] 实现 Signals 页面（信号列表、状态筛选）
- [x] 实现 Paper Trading Positions 页面（持仓列表、PnL 显示）
- [x] 实现 Paper Trading Performance 页面（绩效图表、统计）
- [x] 实现 Event Window 状态指示器（顶部导航栏）

## 验收标准

- [x] 系统可以连续生成 30 条以上信号
- [x] 每条信号都有明确理由（reason 字段不为空）
- [x] 每条信号都有入场、退出和风控参数
- [x] 模拟交易结果可以被完整复盘
- [x] 事件窗口切换正确
- [x] 同一 token 不会在短时间内生成重复信号
- [x] Paper trading 正确模拟买卖和盈亏
- [x] 前端可以查看信号列表和 paper position 详情
- [x] 前端可以查看 paper trading 总体表现

# Signal Flip-Flop Fix：涨跌预测频繁翻转问题修复

## 问题描述

系统在极端时间（数分钟内）向用户推送截然相反的涨跌预测（如"综合看涨"后立即"综合看跌"），原因在于两套独立的推送通道各自以最小间隔反复判定方向，且缺乏方向滞回和确认机制。

## Root Cause 全景

```
                  ┌──────────────────┐
                  │  60s 轮询周期     │
                  └────────┬─────────┘
                           │
            ┌──────────────┴──────────────┐
            │                              │
    ┌───────▼────────┐          ┌─────────▼─────────┐
    │ Signal Engine   │          │ Pot PnL Monitor   │
    │  • 2 快照比较    │          │  • 3 快照判方向    │
    │  • price 阈值 ±10│          │  • 5 分钟冷却      │
    │  • 6h 冷却       │          │                    │
    └───────┬─────────┘          └─────────┬──────────┘
            │                              │
            │  各自独立判断方向              │
            │  无方向记忆                    │
            │  无跨通道协调                  │
            ▼                              ▼
    ┌───────────────────────────────────────────┐
    │           用户收到相反预测                   │
    │  10:00 → "Agent A 综合看涨"                  │
    │  10:03 → "Agent A 子池 PnL 看跌"             │
    │  10:05 → "Agent A 价格暴跌"                   │
    └───────────────────────────────────────────┘
```

### 具体根因

| # | 根因 | 涉及模块 | 影响 |
|---|------|---------|------|
| 1 | **方向判定无确认机制**：每次轮询独立判定，单次异常数据直接触发信号 | signal_engine, pot_monitor | 最严重 |
| 2 | **无平滑/EMA**：combined_surge/dump 分数每次从零算，阈值 35 附近震荡翻转 | signal_engine | 高频 |
| 3 | **价格信号阈值过窄**：`price_change_1h >= 10%` 看涨 vs `<= -8%` 看跌，波动行情反复跨线 | signal_engine | 中频 |
| 4 | **Pot PnL 冷却过短**：5 分钟冷却 + 3 点方向判定，噪声下方向无法稳定 | pot_monitor | 高频 |
| 5 | **两通道完全独立**：Signal Engine 和 Pot PnL Monitor 各自推送，无交集冷却 | scheduler | 中频 |
| 6 | **通知去重只防重复 ID**：FeishuNotifier 每次新建，内存去重失效（`scheduler.py` 行 266） | scheduler | 低频 |

## 解决方案架构

### 核心思路

引入 **Signal State Manager** — 一个集中式方向状态管理器，在两个模块之间共享：

```
                    ┌─────────────────────────┐
                    │   SignalStateManager    │
                    │  ┌───────────────────┐  │
                    │  │  Entity State:    │  │
                    │  │  • 方向确认计数器   │  │
                    │  │  • EMA 平滑分数    │  │
                    │  │  • 上次推送时间/方向 │  │
                    │  │  • 方向冷却计时器   │  │
                    │  └───────────────────┘  │
                    └───────────┬─────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                 │
    ┌─────────▼──────┐  ┌─────▼────────┐  ┌─────▼──────────┐
    │ Signal Engine   │  │ Pot PnL     │  │ Trade Decision │
    │ → 使用 EMA 分数  │  │ → 确认后发   │  │ → 使用平滑分数  │
    │ → 确认后发信号   │  │ → 方向冷却   │  │ → 引用方向状态  │
    │ → 方向冷却       │  │              │  │                 │
    └─────────────────┘  └──────────────┘  └─────────────────┘
```

### 三大机制

#### 机制 1：方向确认计数（Confirmation Count）

```
轮询周期   Reading   方向    计数器
─────────────────────────────────────
T+0       bullish   ↑       1/3 (pending)
T+1       bullish   ↑       2/3 (pending)  
T+2       bullish   ↑       3/3 ✅ CONFIRMED → 允许推送
T+3       bearish  ↓       计数器重置 → 1/3 (pending)
```

- 连续 N 次（默认 3 次 = 3 分钟）同方向才确认推送
- 中间任意一次方向偏离就重置计数器
- 推送后计数器重置

#### 机制 2：EMA 分数平滑

```
ema_score = α × raw_score + (1 − α) × prev_ema_score
（α = 0.3，默认）
```

- 用 ema_score 替代 raw_score 判断 combined_surge/dump 阈值
- 单次异常数据的影响从 100% 衰减到 30%
- 初始值：第一轮 raw_score，后续迭代平滑

#### 机制 3：方向推送冷却（Direction Cooldown）

```
Agent A 10:00 推送 bullish
→ Agent A 在 30 分钟内不可推送 bearish（无论哪个通道）
→ Agent A 在 6h 内不可推送任何信号（保持原有全局冷却）
```

- **短冷却**（30 分钟）：防止同实体推送相反方向
- **长冷却**（6 小时）：保持原有 Signal Engine 全局冷却，防止重复骚扰
- **跨通道生效**：Pot PnL Monitor 推送的 bearish 也会阻挡 Signal Engine 的 bullish

## 实现阶段

### Phase A：核心基础设施 — SignalStateManager

创建 `backend/signals/signal_state.py`，包含两个类：

1. `SignalDirectionState` — 单个实体的方向状态（dataclass）
   - `entity_id: str`
   - `entity_type: Literal["agent", "sub_pot"]`
   - `readings: list[str]` — 最近 N 次方向读数历史
   - `ema_score: float` — EMA 平滑后的综合分
   - `last_notified_direction: str | None`
   - `last_notified_at: float | None` — monotonic time

2. `SignalStateManager` — 管理器
   - `record_reading(entity_id, direction, score) → (confirmed, final_direction)`
   - `can_notify(entity_id, direction) → bool`
   - `mark_notified(entity_id, direction)`
   - `get_smoothed_score(entity_id, raw_score) → float`
   - 可配置参数：`confirmation_count`, `ema_alpha`, `direction_cooldown`, `global_cooldown`

### Phase B：Signal Engine 集成

修改 `backend/signals/signal_engine.py`：

- `__init__` 接受 `SignalStateManager` 参数
- `_analyze()` 完成后，将综合分数通过 StateManager EMA 平滑后再比较阈值
- `run_check()` 中调用 `state_mgr.record_reading()` 获取确认状态
- 只有 `confirmed=True` 的实体才允许构造 Alert
- 保持原有 6h 全局冷却作为第二道防线

### Phase C：Pot PnL Monitor 集成

修改 `backend/monitoring/pot_monitor.py`：

- `check_sub_pot_changes()` 接受 `SignalStateManager` 参数
- 判定方向后通过 `state_mgr.record_reading()` 获取确认状态
- 只有 `confirmed=True` 的才进入后续严重度计算
- 推送前调用 `state_mgr.can_notify()` 检查方向冷却
- 推送后调用 `state_mgr.mark_notified()`

### Phase D：调度器集成

修改 `backend/scheduler/scheduler.py`：

- 在 `run_collection()` 中创建共享 `SignalStateManager` 实例
- 同时传递给 `SignalEngine` 和 `PotPnlMonitor`
- 移除 `_pot_pnl_cooldown` 模块级变量，由 StateManager 统一管理

### Phase E：配置和微调

- 调整 `pot_monitor.py` 的 `_predict_direction()` 快照窗口从 3 个扩展到 5 个
- Pot PnL `_POT_PNL_COOLDOWN_SECONDS` 从 300 提升到 900

## 变更文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **新建** | `backend/signals/signal_state.py` | SignalStateManager 实现 |
| **修改** | `backend/signals/signal_engine.py` | 集成 EMA + 确认计数 |
| **修改** | `backend/monitoring/pot_monitor.py` | 集成确认计数 + 方向冷却 |
| **修改** | `backend/scheduler/scheduler.py` | 创建并注入共享 StateManager |
| **不变** | `backend/config/settings.py` | 暂不新增配置项，使用默认值 |

## 边界情况处理

| 场景 | 处理方式 |
|------|---------|
| 进程重启 | 内存状态丢失 → 重建空 StateManager，前 3 轮为 "warming up" 不推送 |
| 持久无信号 | 24h 无读数的实体自动清理（惰性 TTL） |
| 同一周期 bullish + bearish 同时满足 | conf_count 机制决定哪个方向先达到 3 次；之后方向冷却阻止另一方向 |
| 数据源中断（NaN/None） | reading = "unknown"，不累计任何方向计数器 |
| 多 Agent 并发推送 | 每个 Agent 独立状态，互不影响 |

## 设计原则

1. **状态在内存中**：不需改数据库 schema，进程重启后前 N 轮自动温升
2. **共享不耦合**：StateManager 是纯工具类，SignalEngine 和 PotPnlMonitor 不互相依赖
3. **向下兼容**：不改 Alert/TradeSignal 的模型定义，不改 API 响应格式
4. **无网络依赖**：全部本地计算，不影响采集延迟

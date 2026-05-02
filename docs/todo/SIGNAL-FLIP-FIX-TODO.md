# Signal Flip-Flop Fix — 执行清单

> 参考设计文档：`docs/plan/SIGNAL-FLIP-FIX.md`

---

## Phase A：SignalStateManager 核心实现

### A1：创建 `backend/signals/signal_state.py`

- [ ] 定义 `SignalDirectionState` dataclass：
  - `entity_id: str`
  - `entity_type: Literal["agent", "sub_pot"]`
  - `consecutive_readings: list[str]` — 连续方向读数窗口
  - `ema_score: float` — EMA 平滑分数
  - `last_notified_direction: str | None`
  - `last_notified_at: float | None` — time.monotonic()
  - `last_reading_at: float | None`
- [ ] 定义 `DEFAULT_CONFIG`：`confirmation_count=3`, `ema_alpha=0.3`, `direction_cooldown=1800`, `global_cooldown=21600`, `state_ttl=86400`
- [ ] 实现 `SignalStateManager.__init__(config)` — 用 dict 存储实体状态
- [ ] 实现 `record_reading(entity_id, entity_type, direction, score) -> tuple[bool, str]`：
  - 方向与上轮相同 → 追加到 readings，若达到 confirmation_count → confirmed=True
  - 方向与上轮不同 → 清空 readings 重新计数
  - 更新 ema_score = alpha * score + (1-alpha) * ema
  - 初始值 ema = score, confirmed=False
  - 返回 `(confirmed, ema_adjusted_direction)`
- [ ] 实现 `can_notify(entity_id, direction) -> bool`：
  - 检查方向冷却：上次推送方向 !== direction 且距上次推送 < direction_cooldown → 不可以
  - 检查全局冷却：距上次推送 < global_cooldown → 不可以（保留原 6h 全局冷却）
- [ ] 实现 `mark_notified(entity_id, direction)`：记录推送时间 + 方向
- [ ] 实现 `get_smoothed_score(entity_id, raw_score) -> float`：返回 ema_score
- [ ] 实现 `_cleanup_stale()`：清除超过 state_ttl 未更新的实体
- [ ] 添加模块级日志

## Phase B：Signal Engine 集成

### B1：修改 `backend/signals/signal_engine.py`

- [ ] `SignalEngine.__init__` 增加 `state_manager: SignalStateManager | None = None` 参数
- [ ] `_analyze()` 在 `combined_surge`/`combined_dump` 计算中，使用 state_manager 的平滑分数代替 raw 分数
- [ ] 新增 `_get_direction_from_signals(signals) -> str | None` 方法：从已检测信号中推断整体方向（bullish/bearish/None）
- [ ] `run_check()` 中遍历 agent 时，调用 `state_manager.record_reading()`：
  - 传入 agent_id, "agent", 推断方向, combined_score
  - 仅当 `confirmed=True` 时才继续执行 `_agent_can_alert()` → 生成 Alert
- [ ] 保持 `_agent_can_alert()` + `insert_alert(cooldown_seconds=21600)` 不变
- [ ] 异常保护：`state_manager` 为 None 时跳过所有确认逻辑，行为回退到原状

## Phase C：Pot PnL Monitor 集成

### C1：修改 `backend/monitoring/pot_monitor.py`

- [ ] `PotPnlMonitor.__init__` 增加 `state_manager: SignalStateManager | None = None` 参数
- [ ] `check_sub_pot_changes()` 中 `_predict_direction()` 判定方向后：
  - 映射方向分类为 bullish/bearish：
    - `("up", "steep_up", "recovery_up") → "bullish"`
    - `("down", "steep_down", "pullback_down") → "bearish"`
    - `"stable"` → None
  - 调用 `state_manager.record_reading(sub_pot_id, "sub_pot", direction, abs(pnl_change_pct))`
  - 仅当 confirmed=True 才进入后续 `_compute_severity_tier` + 信号评分
- [ ] 发送通知前调用 `state_manager.can_notify(sub_pot_id, direction)`
- [ ] 发送后调用 `state_manager.mark_notified(sub_pot_id, direction)`
- [ ] 将 `_predict_direction()` 的快照读取从 `limit=3` 改为 `limit=5`
- [ ] 将 `_POT_PNL_COOLDOWN_SECONDS` 从 300 改为 900（15 分钟）

## Phase D：调度器集成

### D1：修改 `backend/scheduler/scheduler.py`

- [ ] 文件顶部导入 `SignalStateManager`
- [ ] 创建模块级实例化函数或在 `run_collection()` 开头创建单例
- [ ] `run_collection()` 中创建 `SignalStateManager`，传入 `SignalEngine` 和 `PotPnlMonitor`
- [ ] 移除 `_pot_pnl_cooldown` 模块级变量（已由 StateManager 替代）
- [ ] 状态管理器传入 PotPnlMonitor 并应用到子池 PnL 监控逻辑块

## Phase E：验证与微调

### E1：验证逻辑

- [ ] 启动后端，观察 3 个完整轮询周期（60s × 3 = 3 分钟），确认：
  - 前 3 轮无警报推送（warming up）
  - 方向连续 3 轮一致后才推送
  - 方向翻转时计数器重置
- [ ] 检查日志输出：StateManager 的 `record_reading` / `can_notify` 决策日志

### E2：模拟场景测试

- [ ] 场景 1：Agent 方向连续 bullish 3 次 → 应推送，第 4 次 bearish 不应推送（方向冷却 + 全局冷却）
- [ ] 场景 2：Agent 方向序列 bullish → bullish → bearish → bullish → bullish → bullish → 前 3 次被重置，第 6 次才推送（连续 3 次 bull）
- [ ] 场景 3：Pot PnL 方向 `up → up → up` → 应推送。5 分钟后 `down → down → down` → 被方向冷却阻挡
- [ ] 场景 4：Pot PnL 先推送 bearish → 5 秒后 Signal Engine 检测到同一 Agent bullish → 被方向冷却阻挡

### E3：死代码清理

- [ ] 确认 `_pot_pnl_cooldown` 模块级变量已移除，无残留引用
- [ ] 确认 `_agent_can_alert()` 中的 `_has_recent_alert()` 未被误删
- [ ] 确认 `FeishuNotifier._dedup_cache` 仍然正常工作（非本任务范围，但确认无回归）

## 验收标准

- [ ] 单一 Agent 在 30 分钟内不会推送相反方向
- [ ] Pot PnL 和 Signal Engine 不会对同一实体推送相反方向
- [ ] 正常趋势延续时推送延迟不超过 3 个轮询周期（3 分钟）
- [ ] 进程重启后自动温升，第 4 轮开始正常推送
- [ ] 连续运行 1 小时无误报
- [ ] 所有改动向后兼容，API 无变化

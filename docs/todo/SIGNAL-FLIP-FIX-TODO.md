# Signal Flip-Flop Fix — 执行清单

> 参考设计文档：`docs/plan/SIGNAL-FLIP-FIX.md` · `docs/plan/PREDICTION-REDESIGN.md`

---

## Phase A：SignalStateManager 核心实现

### A1：创建 `backend/signals/signal_state.py`

- [x] 定义 `SignalDirectionState` dataclass
- [x] 定义 `DEFAULT_CONFIG`
- [x] 实现 `SignalStateManager.__init__(config)`
- [x] 实现 `record_reading() -> tuple[bool, Direction | None, float]`
- [x] 实现 `can_notify(entity_id, direction) -> bool`（方向冷却 + 全局冷却）
- [x] 实现 `mark_notified(entity_id, direction)`
- [x] 实现 `get_smoothed_score(entity_id, raw_score) -> float`
- [x] 实现 `_lazy_cleanup()`（每小时清理过期实体）

## Phase B：Signal Engine 集成

### B1：修改 `backend/signals/signal_engine.py`

- [x] `SignalEngine.__init__` 增加 `state_manager` 参数
- [x] 重写 `_analyze()` 使用趋势检测替代瞬时比较
- [x] 移除 `price_surge`/`price_dump` 信号（用价格预测价格，无因果逻辑）
- [x] `volume_spike` 降级为辅助数据，不推送
- [x] 实现 `_detect_trend()` 滑动窗口趋势检测（N 个快照，80%+ 方向一致）
- [x] 排名趋势：中位数变化 ≥ 3 位才有效
- [x] PnL 阈值提高（涨 ≥ 15%，跌 ≤ -12%）+ pnl_7d 趋势确认
- [x] `run_check()` 中集成 `state_manager.record_reading()` 方向确认
- [x] `_agent_can_alert()` + `insert_alert(cooldown)` 保持
- [x] 修复 PnL 趋势符号反转（`_detect_trend` 设计为 rank 越小越好，PnL 需取反）

## Phase C：Pot PnL Monitor 集成

### C1：修改 `backend/monitoring/pot_monitor.py`

- [x] `PotPnlMonitor.__init__` 增加 `state_manager` 参数
- [x] `check_sub_pot_changes()` 中方向映射 + `record_reading()` 确认
- [x] 未确认方向时跳过本轮
- [x] 快照读取从 `limit=4` 改为 `limit=6`

## Phase D：调度器集成

### D1：修改 `backend/scheduler/scheduler.py`

- [x] 导入 `SignalStateManager`
- [x] `run_collection()` 中创建共享 `state_manager` 实例
- [x] 注入 `SignalEngine` 和 `PotPnlMonitor`
- [x] `can_notify()` / `mark_notified()` 应用于 Pot PnL 通知
- [x] `_POT_PNL_COOLDOWN_SECONDS` 从 300 改为 900

## Phase E：测试验证

### E1：单元测试

- [x] `_detect_trend` 对 rank 序列的正确性（improving → up, worsening → down, oscillation → stable）
- [x] `_detect_trend` 不足 4 个快照时返回 stable
- [x] PnL 取反后方向正确
- [x] 综合信号评分逻辑
- [x] 方向确认（2 次连续读数后才推送）
- [x] 冷却机制（推送后不再重复）

### E2：集成测试

- [x] 完整 surge 场景：信号生成 → 方向确认 → 聚合预警 → cooldown
- [x] 完整 dump 场景：同上（bearish 方向）

### E3：修复中发现的 Bug

- [x] **PnL 趋势符号倒置**：`_detect_trend` 使用 `diff = older - newer`，对 rank（越小越好）正确，对 PnL（越大越好）符号相反。修复：调用时传 `[-v for v in pnl_7d_values]`
- [x] **dict 不可哈希**：`_build_aggregated_alert()` 中 `{s for s in signals}` 创建 set，dict 不可哈希。修复：改用 list comprehension

## 验收标准

- [x] 单一 Agent 不会同轮推送双向信号（方向分组确认）
- [x] Pot PnL 和 Signal Engine 不会对同一实体推送相反方向（共享 SignalStateManager）
- [x] 趋势检测要求 80%+ 方向一致，中位数变化 ≥ 阈值
- [x] PnL surge ≥ 15%，dump ≤ -12%（阈值提高）
- [x] 进程重启后需重新温升达到确认计数
- [ ] 连续运行 1 小时观察翻转率（需部署后验证）

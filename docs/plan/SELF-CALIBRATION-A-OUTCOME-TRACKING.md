# 自校准机制 — 方案 A：预测结果追踪 + 精度反馈

## 核心思路

记录每次预警的预测方向，事后比对实际涨跌，统计各信号类型的命中率。命中率反馈到参数配置，形成自动调节闭环。

```
预警推送 → 记录预测方向 + 当前信号参数
    ↓ (等待观察窗口)
回检实际走势 → 比对预测方向 → 更新命中率统计
    ↓
命中率异常 → 自动调整阈值/确认次数
```

## 设计细节

### 1. 数据库：`signal_outcomes` 表

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,       -- surge / dump / rank_surge / rank_dump / combined_surge / combined_dump / wr_surge / wr_dump
    direction TEXT NOT NULL,          -- bullish / bearish
    score REAL NOT NULL DEFAULT 0,
    params_snapshot TEXT NOT NULL,    -- 推送时的参数快照（JSON）
    
    predicted_at TEXT NOT NULL,       -- 预警时间
    outcome_window_start TEXT,        -- 观察窗口起始
    outcome_window_end TEXT,          -- 观察窗口结束
    
    price_before REAL,                -- 观察期前 Agent Token 价格
    price_after REAL,                 -- 观察期后 Agent Token 价格
    rank_before INTEGER,              -- 观察期前排名
    rank_after INTEGER,               -- 观察期后排名
    pnl_24h_before REAL,             -- 观察期前 24h PnL
    pnl_24h_after REAL,              -- 观察期后 24h PnL
    
    outcome INTEGER,                  -- NULL=待回检, 1=正确, 0=错误, -1=无法判断(数据不足)
    confirmed_at TEXT,                -- 回检时间
    UNIQUE(alert_id)
);
```

### 2. 结果评估规则

评估标准（使用加权评分判断正确性）：

| 信号类型 | 看涨正确条件 | 看跌正确条件 | 观察窗口 |
|----------|-------------|-------------|---------|
| surge / dump | rank 改善 ≥ 2 位 或 PnL_24h ↑≥ 5% 或 价格 ↑≥ 3% | rank 恶化 ≥ 2 位 或 PnL_24h ↓≥ 5% 或 价格 ↓≥ 3% | 30 min |
| rank_surge / rank_dump | rank 改善 ≥ 3 位 | rank 恶化 ≥ 3 位 | 30 min |
| wr_surge / wr_dump | win_rate ↑≥ 3pp | win_rate ↓≥ 3pp | 2 h |
| combined_surge / combined_dump | 多数因子改善（2/3 以上） | 多数因子恶化（2/3 以上） | 1 h |

### 3. 反馈调节算法

每 N 条记录进行一次统计（N = 50 或每天一次），按信号类型分组计算：

```python
hit_rate = correct_count / (correct_count + wrong_count) * 100

if hit_rate < LOWER_BOUND (40%):
    # 该信号类型不准 → 收紧
    threshold *= 1.15        # 提高触发阈值
    confirmation_count += 1  # 增加确认次数

elif hit_rate > UPPER_BOUND (75%):
    # 该信号类型太保守 → 放松
    threshold *= 0.9         # 降低触发阈值
    # 但不下调 confirmation_count（宁缺毋滥）

else:
    # 命中率在合理范围，微调阈值回中
    threshold *= 1.0         # 保持不变
```

**调节参数映射：**

| 信号类型 | 可调阈值参数 | 默认 | 范围 |
|----------|-------------|------|------|
| surge | pnl_surge_min_24h | 15.0 | [10.0, 30.0] |
| dump | pnl_dump_max_24h | -12.0 | [-25.0, -8.0] |
| rank_surge | rank_trend_min_magnitude | 3 | [2, 8] |
| rank_dump | rank_trend_min_magnitude | 3 | [2, 8] |
| wr_surge | wr_surge_min | 8.0 | [5.0, 15.0] |
| wr_dump | wr_dump_max | -8.0 | [-15.0, -5.0] |
| combined | combined_surge_score / combined_dump_score | 35 | [25, 50] |
| 全局 | confirmation_count | 3 | [2, 5] |
| 全局 | direction_cooldown | 1800 | [900, 3600] |

### 4. 实现模块

#### 新增文件：`backend/calibration/outcome_tracker.py`

```
OutcomeTracker
├── record_alert(outcome_tracker, alert, params)  — 预警时写入 signal_outcomes
├── check_outcomes()                                — 定期回检待评估的预警
│   ├── _evaluate_surge_outcome()
│   ├── _evaluate_rank_outcome()
│   ├── _evaluate_wr_outcome()
│   └── _evaluate_combined_outcome()
├── get_hit_rate(signal_type, window) → float       — 查询命中率
└── auto_tune() → dict                              — 生成参数调整建议
    ├── _should_tighten(signal_type) → bool
    ├── _should_loosen(signal_type) → bool
    └── _calculate_new_threshold(signal_type) → float
```

#### 修改文件：`backend/signals/signal_state.py`

- `AutoTuneConfig` dataclass：存储可动态调节的参数（替代部分 DEFAULT_CONFIG）
- `SignalStateManager.apply_tuning(params: dict)` 方法：应用自动调节后的参数

#### 修改文件：`backend/scheduler/scheduler.py`

- 新增定时任务 `outcome_check_job`（每 30 分钟执行一次回检）
- 新增定时任务 `auto_tune_job`（每天凌晨执行一次）

## 优点与风险

**优点：**
- 形成完整反馈闭环
- 命中率可量化，知道每个信号类型准确度
- 调节幅度可控，不会剧烈变化

**风险：**
- 需要 Agent Token 价格数据（并非所有 Agent 都有 token）
- 观察窗口长度影响判定结果——太短会被噪声干扰，太长错过及时调节
- 低样本量下统计无意义（前几周数据积累期）

## 验证指标

- 部署后 1 周：命中率 ≥ 50%（随机水平）
- 部署后 2 周：命中率 ≥ 60%
- 部署后 1 个月：命中率 ≥ 65%，且浮动 < 10%
- 无同 Agent 同轮双向推送回归

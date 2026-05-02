# 自校准机制 — 方案 D：全自动校准

## 核心思路

定期用历史快照数据做回测，网格搜索最优参数组合。以 F1 分数（或加权指标）为优化目标，自动更新生产配置。

```
历史快照数据
    ↓
生产环境当前参数 → 回测模拟 → 计算 F1/Precision/Recall
    ↓
网格搜索（参数组合空间） → 找到最优参数
    ↓
对比生产参数与最优参数
    ↓
差异超过阈值 → 自动更新配置
```

## 设计细节

### 1. 回测引擎

用历史快照数据模拟信号引擎运行，比对信号预测方向与实际走势。

```python
class BacktestEngine:
    """
    用历史数据回测信号引擎
    
    输入：时间范围、参数配置、Agent 列表
    输出：信号记录 + 每个信号的事后判定结果
    """
    
    def __init__(self, database: Database):
        self.db = database
        
    def run(
        self,
        start_time: str,
        end_time: str,
        params: dict,           # SIGNAL_THRESHOLDS 覆盖
        agent_ids: list[str] | None = None,  # None = 全部
    ) -> BacktestResult:
        """运行一次回测"""
        
        # 1. 按时间分片推进（模拟实时采集）
        # 2. 每个时间点用指定参数运行 SignalEngine
        # 3. 记录每个触发的信号
        # 4. 跨过观察窗口后判定信号是否正确
        # 5. 返回统计结果
        
        ...

@dataclass
class BacktestResult:
    total_signals: int
    true_positives: int       # 正确预警
    false_positives: int      # 误报
    false_negatives: int      # 漏报（未触发但实际发生了）
    
    precision: float           # TP / (TP + FP)
    recall: float              # TP / (TP + FN)
    f1_score: float            # 2 * precision * recall / (precision + recall)
    
    by_signal_type: dict[str, SignalTypeResult]  # 按信号类型拆分
    params_used: dict                             # 回测使用的参数
```

### 2. 漏报检测

漏报（false negative）是"应该预警但没有预警"的情况，需要定义触发条件：

```python
def _detect_false_negatives(
    agent_snapshots: list[dict],
    triggered_alerts: list[Alert],
) -> list[MissedSignal]:
    """
    检查是否有应该触发但未触发的情况。
    
    判定标准（任一满足即为"应该触发"）：
    - 排名 20 分钟内变化 ≥ 8 位
    - PnL_24h 从 <10% 跳变到 ≥ 15% 或从 >-8% 跌到 ≤ -12%
    - 胜率 1 小时内变化 ≥ 10pp
    """
    ...
```

### 3. 网格搜索空间

| 参数 | 搜索范围 | 步长 |
|------|---------|------|
| rank_trend_min_magnitude | [2, 3, 4, 5, 6, 8] | 离散 |
| rank_trend_consistency | [0.7, 0.75, 0.8, 0.85, 0.9] | 0.05 |
| pnl_surge_min_24h | [10, 12, 15, 18, 20, 25] | 离散 |
| pnl_dump_max_24h | [-20, -18, -15, -12, -10] | 离散 |
| wr_surge_min | [5, 8, 10, 12, 15] | 离散 |
| wr_dump_max | [-15, -12, -10, -8, -5] | 离散 |
| combined_surge_score | [25, 30, 35, 40, 45, 50] | 离散 |
| combined_dump_score | [25, 30, 35, 40, 45, 50] | 离散 |
| confirmation_count | [2, 3, 4, 5] | 离散 |

总计约 93312 种组合（6×5×6×5×5×5×6×6×4）。需要优化策略减少搜索量。

### 4. 搜索优化策略

**策略 1：分阶段搜索**

```
Phase 1: 独立优化每个信号类型（忽略其他信号类型参数）
  - 只调 rank 参数，固定其他为默认值
  - 只调 PnL 参数，固定其他为默认值
  - 只调 win_rate 参数，固定其他为默认值
  → 得到每个信号类型的局部最优

Phase 2: 联合优化
  - 以 Phase 1 结果为起点
  - 小范围搜索参数组合的交集区域
  - 优化目标是整体 F1 分数

Phase 3: 验证
  - 用 Phase 2 结果在不同时间窗口运行
  - 确认无过拟合
```

组合数：Phase 1 约 6+5+5+5+5+5 = 31 次 × 信号类型权重，Phase 2 约 64-128 次。总计约 200 次回测，每次约 1-3 秒 → 5-10 分钟可完成一次全校准。

**策略 2：贝叶斯优化**

用 `scikit-optimize` 或类似库替代网格搜索，用高斯过程建模参数与 F1 的关系，更快收敛到最优区域。预计 30-50 次迭代即可找到接近最优的解。

### 5. 实现模块

#### 新增文件：`backend/calibration/auto_calibrator.py`

```
AutoCalibrator
├── __init__(database)
├── full_calibrate() → CalibrationResult
│   ├── _phase1_individual_optimize()
│   ├── _phase2_joint_optimize()
│   └── _phase3_validate()
├── quick_calibrate() → CalibrationResult
│   └── 只调 3 个最敏感参数（rank_mag, pnl_threshold, combined_score）
├── _grid_search(param_space, objective) → dict
├── _objective(params) → float
│   └── 运行回测，返回 -F1（优化器最小化负 F1）
└── _apply_params(params) → None
    └── 更新 SIGNAL_THRESHOLDS + 持久化到数据库
```

#### 新增文件：`backend/calibration/backtest.py`

```
BacktestEngine（见上）
```

#### 新增文件：`backend/db/migrations.py`

- `signal_calibration_params` 表，存储每次校准记录

```sql
CREATE TABLE IF NOT EXISTS signal_calibration_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibrated_at TEXT NOT NULL,
    params JSON NOT NULL,             -- 完整参数快照
    f1_score REAL NOT NULL,
    precision REAL NOT NULL,
    recall REAL NOT NULL,
    total_signals INTEGER NOT NULL,
    time_range_start TEXT NOT NULL,
    time_range_end TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0  -- 当前是否生效
);
```

#### 修改文件：`backend/scheduler/scheduler.py`

- 新增定时任务 `auto_calibrate_job`（每天凌晨 3:00 执行一次）

### 6. 安全机制

自动校准的侵入性最强，必须设计安全边界：

```
安全检查（每次校准后）：
1. 新参数 F1 必须 ≥ 旧参数 F1 × 0.95（不能下降超过 5%）
2. 新参数不能在 24 小时内导致超过 50 条 Alert（防止参数过松）
3. 保留前 3 次校准的参数用于快速回滚
4. 自动校准可由 api/health 端点的手动开关禁用

回滚机制：
- signal_calibration_params 表保留最近 5 条记录
- /api/v1/calibration/rollback API 可手动回滚到任意历史版本
- 进程重启时加载 active=1 的参数
```

## 方案对比

| 维度 | 方案 A | 方案 B | 方案 C | 方案 D |
|------|--------|--------|--------|--------|
| 复杂度 | 低-中 | 中 | 中 | 高 |
| 数据需求 | 预警+回检 | Agent 快照 | Agent 快照 | 全部历史 |
| 见效时间 | 1-2 周 | 即时 | 即时 | 1 天 |
| 安全风险 | 低 | 低 | 低 | 中（需安全网） |
| 维护成本 | 低 | 低 | 低 | 中 |
| 可解释性 | 高 | 高 | 高 | 中（黑盒优化） |
| 独立部署 | ✅ | ✅ | ✅ | ❌ 依赖 A 的结果定义 |

**推荐路径：A → B → C → D**

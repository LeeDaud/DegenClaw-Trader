# 自校准机制 — 方案 B：Agent 自适应灵敏度

## 核心思路

不同 Agent 的波动特性不同。当前统一阈值对所有 Agent 一视同仁，导致高波动 Agent 频繁误报、低波动 Agent 信号不足。按每个 Agent 的历史指标波动率动态缩放阈值。

```
Agent A（低波动，排名 ±2 位振荡）
  统一阈值 = 3 位 → 有效过滤噪声 ✓
  
Agent B（高波动，排名 ±8 位振荡）
  统一阈值 = 3 位 → 持续误报 ✗
  应动态调整到 8 位
```

## 设计细节

### 1. Agent 波动率计算

每个 Agent 维护滚动窗口的指标波动率：

```python
class AgentVolatility:
    """Agent 各指标的历史波动率"""
    agent_id: str
    rank_volatility: float        # 排名波动率（std of rank_diff over window）
    pnl_24h_volatility: float     # PnL 波动率
    win_rate_volatility: float    # 胜率波动率
    sample_count: int             # 采样数
    window_minutes: int           = 60   # 默认 1 小时滚动窗口
    decay_factor: float           = 0.9  # 指数衰减系数（旧数据权重递减）
```

计算方法：

```python
# 滚动窗口中的排名差值序列
rank_diffs = [abs(snapshots[i].rank - snapshots[i+1].rank) 
              for i in range(len(snapshots)-1)]

# 加权标准差（越新的数据权重越高）
weights = [decay_factor ** (len(rank_diffs) - i) for i in range(len(rank_diffs))]
avg = sum(d * w for d, w in zip(rank_diffs, weights)) / sum(weights)
variance = sum(w * (d - avg)**2 for d, w in zip(rank_diffs, weights)) / sum(weights)
volatility = sqrt(variance)
```

### 2. 阈值缩放公式

为每个信号类型计算缩放后的阈值：

```python
def scaled_threshold(base_threshold, volatility, agent_metric_volatility):
    """
    base_threshold: 全局基础阈值（如 rank_trend_min_magnitude = 3）
    volatility:     该 Agent 该指标的波动率
    agent_metric_volatility: 全市场该指标的波动率中位数
    
    Returns: 缩放后的阈值
    """
    if volatility <= 0 or agent_metric_volatility <= 0:
        return base_threshold
    
    ratio = volatility / agent_metric_volatility
    
    # 波动率是市场均值的 N 倍 → 阈值同比放大
    # 但限制缩放范围 [0.5x, 3x]
    scaled = base_threshold * ratio
    return clamp(scaled, base_threshold * 0.5, base_threshold * 3.0)
```

**示例：**

| Agent | 排名波动率 | 市场均值 | 缩放比 | 原始阈值 | 缩放后 |
|-------|-----------|---------|-------|---------|-------|
| A | 1.5 | 3.0 | 0.5x | 3 | 1.5 → 2 (clamped) |
| B | 3.0 | 3.0 | 1.0x | 3 | 3.0 |
| C | 8.0 | 3.0 | 2.67x | 3 | 8.0 |

### 3. 信号强度标准化

统一不同波动率 Agent 的信号强度，使比较公平：

```python
def normalized_score(raw_score, volatility, base_volatility=3.0):
    """将原始分数归一化到标准波动率下的等效分数"""
    if volatility <= 0:
        return raw_score
    return raw_score * (base_volatility / volatility)
```

这样，高波动 Agent 的巨大排名变化会被降权，低波动 Agent 的小幅变化会被加权——在综合信号评分中更公平地比较不同 Agent。

### 4. 实现模块

#### 新增文件：`backend/calibration/agent_volatility.py`

```
AgentVolatilityTracker
├── __init__(database, window_minutes=60, decay_factor=0.9)
├── get_volatility(agent_id, metric) → float
│   └── 计算指定指标的滚动波动率
├── get_all_volatilities() → dict[str, dict[str, float]]
│   └── 返回所有 Agent 的所有指标波动率
├── get_market_median_volatility(metric) → float
│   └── 全市场该指标波动率中位数（排除异常值）
├── _fetch_snapshots(agent_id, limit) → list[dict]
├── _calc_rank_volatility(snapshots) → float
├── _calc_pnl_volatility(snapshots) → float
└── _calc_wr_volatility(snapshots) → float
```

#### 修改文件：`backend/signals/signal_engine.py`

- `SignalEngine.__init__` 增加 `volatility_tracker: AgentVolatilityTracker | None = None`
- `_analyze()` 中获取阈值时使用 `scaled_threshold()` 替代直接读 `SIGNAL_THRESHOLDS`
- 综合信号评分中使用 `normalized_score()` 

#### 修改文件：`backend/signals/signal_state.py`

- 在 EMA 平滑中使用 normalized_score 替代 raw_score

## 优点与风险

**优点：**
- 解决核心矛盾：不同 Agent 波动性差异大
- 自适应，无需手动配置
- 高波动 Agent 不再频繁误报

**风险：**
- 新 Agent 无历史数据 → 需要初始默认值（用市场均值）
- 异常 Agent（几乎不波动）→ 阈值被过度压低 → 需要 clamp 下限
- 波动率突变（Agent 策略变更）→ 需要足够采样才能追上 → decay factor 决定响应速度

## 扩展：seasonal volatility

Agent 的波动率在不同比赛阶段可能不同：
- 赛季初期（新 Agent 涌入）：波动大
- 赛季中段：趋于稳定
- 赛季末（Council 评定前一周）：波动再次增大

可加入季节性因子（按赛季阶段缩放）：
```python
seasonal_factor = {
    "early": 1.3,    # 初期，放宽阈值
    "mid": 1.0,      # 中期，标准
    "late": 1.2,     # 末期，适当放宽
}
```

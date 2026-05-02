# 自校准机制 — 方案 C：动态趋势检测窗口

## 核心思路

当前趋势检测使用固定窗口（6 个快照，80% 一致率）。信噪比高（趋势清晰）时窗口太长会延迟响应，信噪比低（噪声大）时窗口太短会误报。改为根据实时信噪比动态调整窗口参数。

```
信号强（SNR 高）→ 缩短窗口，更快响应
  例：Agent 连续 4 轮单边改善 → 只需 4 个快照即可确认
  
信号弱（SNR 低）→ 拉长窗口，提高置信度
  例：Agent 在 ±3 位振荡 → 需要 8-10 个快照才能确认趋势
```

## 设计细节

### 1. 信噪比计算

```python
def calculate_snr(values: list[float]) -> float:
    """
    计算时间序列的信噪比（Signal-to-Noise Ratio）
    
    Signal = abs(latest - mean)     # 当前偏离均值幅度
    Noise  = std(values)            # 整体波动程度
    
    Returns: SNR 值（越大信号越清晰）
    """
    if len(values) < 3:
        return 0.0
    
    arr = np.array(values)
    signal = abs(arr[0] - arr.mean())  # 最新值与均值偏差
    noise = arr.std()                  # 总体标准差
    
    if noise == 0:
        return float('inf')
    
    return signal / noise
```

### 2. 动态窗口参数映射

| SNR 范围 | 窗口大小（快照数） | 一致率阈值 | 含义 |
|----------|------------------|-----------|------|
| SNR ≥ 3.0 | 4 | 75% | 信号极强，快速确认 |
| SNR ≥ 1.5 | 6 | 80% | 信号明确，标准窗口 |
| SNR ≥ 0.8 | 8 | 85% | 信号较弱，拉长确认 |
| SNR < 0.8 | 10 | 90% | 噪声主导，需要强证据 |

### 3. 趋势强度缓存

为避免每轮都重新计算同一组快照的 SNR，使用趋势强度缓存：

```python
class TrendSignalCache:
    """
    缓存最近一次趋势检测结果，避免重复计算。
    当新快照产生时，标记缓存失效。
    """
    _cache: dict[str, TrendResult]   # key = f"{agent_id}:{metric}"
    _ttl_seconds: int = 60           # 缓存有效期
    
    def get(self, agent_id, metric) -> TrendResult | None
    def set(self, agent_id, metric, result)
    def invalidate(self, agent_id, metric=None)
```

### 4. 信号优先级

动态窗口产生的信号携带置信度等级，用于决定通知优先级：

```python
class ConfidenceLevel(Enum):
    HIGH = 3    # 短窗口 + 高 SNR → 立即推送
    MEDIUM = 2  # 标准窗口 → 按现有逻辑处理
    LOW = 1     # 长窗口才确认 → 仅在严重时才推送

# 综合信号评分乘以置信度因子
adjusted_score = raw_score * (confidence_level.value / 2.0)
```

**推送决策结合置信度：**

| 置信度 | 严重度 high/critical | 严重度 medium | 严重度 low |
|--------|---------------------|--------------|-----------|
| HIGH | ✅ 推送 | ✅ 推送 | ❌ 不推送 |
| MEDIUM | ✅ 推送 | ✅ 推送 | ❌ 不推送 |
| LOW | ✅ 推送 | ❌ 不推送 | ❌ 不推送 |

### 5. 实现模块

#### 修改文件：`backend/signals/signal_engine.py`

- `_detect_trend()` 增加 `snr_based_dynamic_window()` 调用
- 新增 `_calc_snr(values)` 静态方法
- `_get_window_config(snr)` 方法：根据 SNR 返回 `(window_size, consistency_threshold)`
- 每次调用 `_detect_trend` 时先计算 SNR，再用动态参数

```python
def _detect_trend(
    values: list[float],
    consistency_threshold: float | None = None,   # None = 动态计算
) -> tuple[str, float, float]:
    
    snr = self._calc_snr(values)
    window_size, consistency_threshold = self._get_window_config(snr)
    
    # 只取最近 window_size 个快照
    values = values[:window_size]
    
    # 原逻辑...
```

#### 修改文件：`backend/calibration/trend_cache.py`（新增）

```
TrendSignalCache
├── get(agent_id, metric) → TrendResult | None
├── set(agent_id, metric, result)
├── invalidate(agent_id, metric=None)
└── _is_expired(key) → bool
```

## 优点与风险

**优点：**
- 趋势清晰时更快响应（信息差套利窗口小，快很重要）
- 噪声大时更保守（减少误报）
- 自适应，无需手动调整

**风险：**
- SNR 计算引入额外开销（6 个快照很小，可忽略）
- SNR 本身可能受异常值影响 → 用中位数替代均值更鲁棒
- 窗口频繁切换可能导致参数振荡 → 添加滞后阻尼（hysteresis）

**滞后阻尼实现：**

```python
# 避免 SNR 在边界附近频繁切换窗口大小
def _get_window_size(self, snr: float, prev_window: int) -> int:
    if snr >= 3.0:
        return 4 if prev_window > 4 else prev_window  # 只缩不扩
    elif snr >= 1.5:
        return 6
    elif snr >= 0.8:
        return 8
    else:
        return 10 if prev_window < 10 else prev_window  # 只扩不缩
```

## 与方案 A/B 的关系

- **搭配方案 A**：SNR 作为反馈调节的辅助因子—低 SNR 环境下降低预期命中率
- **搭配方案 B**：SNR + Agent 波动率共同决定窗口大小—高波动 Agent 在高 SNR 时也可用短窗口
- 方案 C 独立可部署，不必等 A/B 先上

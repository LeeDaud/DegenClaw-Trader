# 价格反转预警方案

## 1. 需求回顾

在价格连续上涨后出现 1/3/5 根阴线时发飞书预警，连续下跌后出现 1/3/5 根阳线同理。预警附带成交量数据。

## 2. 讨论结论

| 决策点 | 选择 | 理由 |
|--------|------|------|
| K线颗粒度 | 15s~30s（独立高频价格采集） | 不降低主轮询间隔，独立跑快速价格采集 |
| 趋势判定起点 | 3 根连续同向 | 不设固定阈值，按连续根数分档强度 |
| 反转触发级别 | 1/3/5 根均触发 | 按分级严重度推送，各自有冷却 |

## 3. 架构方案

### 核心思路：独立高频价格采集 + 独立烛图分析器

不修改现有采集/信号流程，新增两条独立链路：

```
┌─────────────────────────────────────────────────────┐
│ 现有链路（60s 周期）                                  │
│ DegenClawCollector → Parser → DB                      │
│ MarketCollector → TokenMarketSnapshot → SignalEngine   │
│ → FeishuNotifier                                      │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ 新增链路（15~30s 周期）                               │
│ PriceTicker → price_ticks DB → CandleAnalyzer         │
│ → FeishuNotifier                                     │
└─────────────────────────────────────────────────────┘
```

### 数据流

```
PriceTicker.tick()
  └─ DexScreener 批量接口（30地址/次）获取所有token实时价
  └─ INSERT INTO price_ticks (token_address, price_usd, volume_1h, snapshot_at)

CandleAnalyzer.run_check()
  └─ SELECT FROM price_ticks WHERE token=? ORDER BY snapshot_at DESC LIMIT 50
  └─ 扫描模式 → 判断趋势方向 + 反转计数
  └─ 返回 list[Alert]
  └─ INSERT INTO alerts + FeishuNotifier.send_alerts_batch()
```

### 核心算法

```
从最新向旧扫描 price_usd 序列，方向判定阈值 = ±0.1%（防噪声）。

输入: prices = [最新, ..., 最旧]  (长度 N ≥ 10)

Step 1: 去除 flat（|change| < 0.1% 的相邻对跳过）
Step 2: 从最新开始统计连续同向数 → reversal_count
Step 3: reversal_count 后的第一个方向变化 → trend_length
Step 4: 条件判断
   - trend_length ≥ 3 且 reversal_count ∈ [1, 3, 5] → 触发预警
   - reversal_count 不是 1/3/5 → 跳过（避免每根都推）

严重度计算:
   base_severity = {1: "low", 3: "medium", 5: "high"}
   trend_factor  = trend_length 分档（3-4→1.0, 5-7→1.5, 8-11→2.0, 12+→3.0）
   final_severity = base 按 trend_factor 升级（×1.5 升一级，×2.0 升两级）

成交量:
   反转段对应 price_ticks 中 volume_1h 的最大值或平均值
```

### 状态管理

每个 token 独立维护：
- `current_trend_dir`: 当前趋势方向（up/down/none）
- `trend_streak`: 趋势连续根数
- `max_trend_length`: 本趋势最大连续根数（用于强度分级）
- `last_alert_levels`: 已推送的 1/3/5 级冷却（防重复）

冷却：
- 每个 level 独立冷却，同 level 不重复推（默认 900s/15min）
- 方向变化后自动重置冷却（新趋势开始）

### 数据库变更

新建 `price_ticks` 表：

```sql
CREATE TABLE IF NOT EXISTS price_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_address TEXT NOT NULL,
    price_usd REAL NOT NULL DEFAULT 0.0,
    volume_1h REAL NOT NULL DEFAULT 0.0,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_ticks_token_time
    ON price_ticks(token_address, snapshot_at DESC);
-- 自动清理 1 小时前的旧 tick（保留 240~480 条/token，足够模式识别）
```

新增 Model: `PriceTick`

## 4. 涉及文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/db/models.py` | 修改 | 新增 PriceTick 数据类 |
| `backend/db/database.py` | 修改 | 新增 price_ticks 表 DDL、insert/get/cleanup 方法 |
| `backend/collectors/price_ticker.py` | **新建** | PriceTicker 类：高频采集所有 token 实时价格 |
| `backend/signals/candle_analyzer.py` | **新建** | CandleAnalyzer 类：烛图模式检测 + 反转预警 |
| `backend/notifiers/feishu_notifier.py` | 修改 | 新增 reversal_bearish/bullish 卡片模板 |
| `backend/scheduler/scheduler.py` | 修改 | 新增 price_tick 调度任务，集成 CandleAnalyzer |
| `backend/config/settings.py` | 修改 | 新增 price_tick_interval_seconds 配置 |

## 5. 不涉及的改动

- SignalEngine / SignalStateManager：不改动，烛图分析独立运行
- 评分引擎 / 决策引擎：不涉及
- 前端：本轮不涉及（后续可在 Token Market 页面显示 tick 数据）

## 6. 风险与限制

1. **15s 间隔 vs 真实秒线**：相邻 tick 间价格变化可能很小，导致大量 flat。如果连续 flat，趋势判断会被拉长。
2. **volume_1h 是滑动估算**：不是逐根的真实成交量，仅作为参考。
3. **DexScreener 批量端点可用性**：需验证 `/tokens/v1/{chain}/{addresses}` 是否工作。降级方案是维持单地址逐个请求。
4. **价格变化阈值 0.1%**：对于高度波动的 meme token 可能过低，需运行后观察调整。

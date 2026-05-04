# Pot PnL 飞书预警系统 · 实施规划

## 1. 需求背景

当前 `PotPnlMonitor` 仅有基础 2 级（medium/high）阈值检测和简单方向预判。需要升级为 **4 级严重度 + 多因子看涨/看跌信号系统**，当子池 PnL 突破有意义量级时通过飞书卡片推送通知和趋势信号。

## 2. 4 级严重度定义

### 阈值矩阵

触发值取两者较大值：`trigger = max(pnl_change_pct_of_capital, abs(roi_change))`

其中 `pnl_change_pct_of_capital = (pnl_change / starting_capital) * 100`

| 等级 | 标签 | 相对 Capital 的 PnL % | ROI 变化 | 飞书颜色 | 说明 |
|------|------|----------------------|----------|---------|------|
| T1 | info | >= 3% | >= 2% | blue | 轻微波动，信息通知 |
| T2 | warning | >= 8% | >= 5% | yellow | 值得关注的变动 |
| T3 | important | >= 15% | >= 10% | orange | 重要变动，含建议 |
| T4 | critical | >= 25% | >= 20% | red | 极端变动，紧急推送 |

### 自动升级规则（override tier 至更高级别）

- **符号翻转**（PnL 跨零）：如 `prev_pnl * latest_pnl < 0`，tier 升一级（最低 T2）
- **连续同向**：最近 3 次变化同号，tier 升一级
- **Capital-relative PnL > 40%**：强制 T4

## 3. 信号因子定义

### 因子 A：PnL 方向趋势（权重 2）

基于快照序列的趋势判定：

| 方向 | 分数 | 含义 |
|------|------|------|
| steep_up | +3 | 连续增长且斜率陡峭 |
| up | +2 | 连续 PnL 增长 |
| recovery_up | +1 | V 型反转 |
| stable | 0 | 无明显趋势 |
| pullback_down | -1 | 倒 V 型 |
| down | -2 | 连续 PnL 下降 |
| steep_down | -3 | 连续下降且斜率陡峭 |

### 因子 B：已实现 vs 未实现 PnL 结构（权重 1）

PnL 质量分析（`realized_pnl` vs `unrealized_pnl`）：

| 条件 | 分数 |
|------|------|
| realized > 0 AND unrealized > 0 AND realized/total >= 0.6 | +2 |
| realized > 0 AND unrealized > 0 AND realized/total < 0.6 | +1 |
| realized > 0 AND unrealized <= 0 | -1 |
| realized <= 0 AND unrealized > 0 | +1 |
| realized <= 0 AND unrealized <= 0 | -2 |
| total > 0 AND realized/total >= 0.8 | +2 |
| total < 0 AND abs(realized)/abs(total) >= 0.8 | -2 |

### 因子 C：PnL 符号翻转（权重 3）

| 条件 | 分数 |
|------|------|
| 从亏转盈 | +4 |
| 从盈转亏 | -4 |
| 无符号变化 | 0 |

### 因子 D：持仓数量与健康度（权重 1）

从 positions JSON 解析：

| 条件 | 分数 |
|------|------|
| 6+ 持仓，多数浮盈 | +1 |
| 4-5 持仓，混合 | 0 |
| 1-2 持仓且大额浮亏 | -1 |
| 无持仓 | -1 |

### 因子 E：Agent 胜率（权重 1）

从 `get_latest_agent_snapshot(agent_id)` 获取：

| 条件 | 分数 |
|------|------|
| win_rate > 60% AND trade_count > 10 | +1 |
| win_rate 40-60% | 0 |
| win_rate < 40% AND trade_count > 10 | -1 |

### 信号聚合

```
raw_score = (A * 2) + B + (C * 3) + D + E
```

| raw_score | 信号标签 |
|-----------|---------|
| >= +5 | strong_bullish（强烈看涨） |
| +2 ~ +4 | bullish（看涨） |
| +1 ~ -1 | neutral（中性） |
| -2 ~ -4 | bearish（看跌） |
| <= -5 | strong_bearish（强烈看跌） |

## 4. 飞书卡片设计

### 卡片结构

```
Header: [图标] [信号标签] · [等级标签] · [子池名] ([Agent])
Color: T1=blue / T2=yellow / T3=orange / T4=red

Section 1 — PnL 摘要:
  PnL: $X → $Y (+$Z, +W% of capital)
  ROI: X% → Y% (+Z%)
  信号: [图标] [标签] | 分数: +N

Section 2 — 信号分析 (T2+):
  📊 趋势: [方向]（得分）
  📋 PnL 结构: [已实现 vs 未实现]（得分）
  🎯 信号: [符号变化]（得分）
  📦 持仓: [数量]（得分）
  🏆 Agent: [胜率]（得分）

Section 3 — Callout (T3+):
  T3: "建议关注该子池风险" / "建议关注该子池机会"
  T4: "⚠️ 紧急：PnL 剧烈波动，请立即关注"

Footer: DegenClaw AI Pot Monitor · HH:MM:SS
```

### 图标映射

| 信号 | 图标 |
|------|------|
| strong_bullish | 🟢🟢 |
| bullish | 🟢 |
| neutral | ⚪ |
| bearish | 🔴 |
| strong_bearish | 🔴🔴 |

## 5. 实现步骤

### Step 1: `config/settings.py`

新增 8 个 env var 到 `Settings` dataclass：
- `DC_POT_PNL_TIER_INFO_PCT` / `WARNING` / `IMPORTANT` / `CRITICAL`
- `DC_POT_ROI_TIER_INFO_PCT` / `WARNING` / `IMPORTANT` / `CRITICAL`

保留现有 `pot_pnl_change_threshold` / `pot_roi_change_threshold` 作为抑制门（低于此门限不触发任何提醒）。

### Step 2: `monitoring/pot_monitor.py`

完整重写 `PotPnlMonitor`，保留现有接口签名：

```python
class PotPnlMonitor:
    def __init__(self, database: Database) -> None
    
    def check_sub_pot_changes(
        self, round_id: str, sub_pots: list[dict], settings: Settings
    ) -> list[dict]:
        """主入口：遍历子池 → 抑制门 → 等级判定 → 信号评分 → 返回变更列表"""
    
    # 内部方法
    def _compute_severity_tier(self, pnl_pct, roi_change, prev_pnl, latest_pnl, capital, snapshots, settings) -> str
    def _predict_direction(self, snapshots) -> str  # 增强：斜坡陡峭分类
    def _compute_signal_score(self, sp, snapshots, agent_snapshot) -> dict  # 5 因子评分
    def _calc_pnl_change_pct_of_capital(self, pnl_change, capital) -> float
    
    @staticmethod
    def build_feishu_card(change: dict) -> dict  # 增强卡片
```

### Step 3: `scheduler/scheduler.py`

- 传入 `settings` 对象而非单独阈值参数
- Agent 快照查询移至 monitor 内部

### Step 4: `backend/.env.example`

添加新 env var 文档。

## 6. 数据流

```
run_collection()
  → fetch pot status (sub_pots)
  → upsert sub_pots + insert PnL 快照
  → PotPnlMonitor.check_sub_pot_changes(round_id, sub_pots, settings)
    → 遍历 sub_pot:
      → 取 4 条最近快照
      → 计算 pnl_change (capital-relative %)
      → 计算 roi_change
      → _predict_direction(snapshots)
      → 抑制门检查（旧阈值）
      → _compute_severity_tier(...)
      → get_latest_agent_snapshot(agent_id)
      → _compute_signal_score(...)
      → 组装 change 记录
    → 返回 changes 列表
  → 遍历 changes:
    → build_feishu_card(change)
    → FeishuNotifier.send_card(card)
```

## 7. 边界情况

| 场景 | 处理 |
|------|------|
| starting_capital = 0 | pnl_change_pct 返回 0，降级旧逻辑 |
| 快照不足 2 条 | 跳过，不产生告警 |
| Agent 快照查询失败 | 因子 E 得分 = 0，告警仍触发 |
| Positions JSON 解析失败 | 因子 D 得分 = 0 |
| 全部低于门限 | 返回空列表，无告警 |
| 飞书 webhook 失败 | send_card() 打日志，不崩溃 |

## 8. 验证清单

- [ ] 后端在默认 env 下正常启动
- [ ] PnL 变化 < 3% capital 不产生告警
- [ ] PnL 变化 = 5% → info 级别，简洁卡片
- [ ] PnL 变化 = 10% → warning 级别，完整信号分析卡片
- [ ] PnL 变化 = 20% → important 级别，含建议
- [ ] PnL 变化 = 30% → critical 级别，含紧急标注
- [ ] 从亏转盈：正确 bullish 信号，tier 升级
- [ ] 从盈转亏：正确 bearish 信号，tier 升级
- [ ] 连续 3 次负变化：strong_bearish 信号
- [ ] 飞书卡片颜色随 tier 变化
- [ ] agent win_rate 出现在卡片中
- [ ] pot_monitor_enabled=false 跳过整个监控块
- [ ] 正常运行无异常日志

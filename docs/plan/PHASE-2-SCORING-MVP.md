# Phase 2：评分模型 MVP

## 概述

构建 Agent Scoring Engine，对所有候选 Agent 进行自动评分。Phase 2 产生评分结果，但不产生交易信号。

## 核心目标

1. 实现评分计算引擎（复用 SignalHub score_engine.py 框架）
2. 所有评分因子可配置
3. 评分结果可解释
4. 评分趋势可视化

## 代码复用说明

Phase 2 直接复用 **SignalHub (004)** 的评分框架：

| 复用模块 | 复用的具体能力 |
|---------|--------------|
| `signalhub/app/scoring/score_engine.py` | 多维度加权评分框架、等级标签生成、风险等级判定 |
| `signalhub/app/database/models.py` | 评分数据模型设计模式（ProjectScore → AgentScore）|
| `signalhub/app/database/db.py` | upsert 评分结果 |

**复用方式：** 继承 `ScoreEngine` 基类，重写评分因子计算方法，保留加权计算和等级标签框架。

```python
from scoring.score_engine import ScoreEngine

class DegenClawScoreEngine(ScoreEngine):
    """继承 SignalHub 评分框架"""
    
    def score(self, agent: AgentData, market: MarketData) -> ScoreResult:
        # 保留父类的加权计算机制
        # 替换评分因子为 DegenClaw 专用指标
        ...
```

详见 [REUSE-STRATEGY.md](REUSE-STRATEGY.md)。

## 评分模型总览

```
总分 100 分（风险扣分最多 -20 分）

├── AI Council 入选概率分 (0-35)
│   ├── 排名接近 top 10 (0-15)
│   ├── 历史入选加分 (0-10)
│   ├── 排名连续上升 (0-5)
│   └── 长期稳定 top 20 (0-5)
│
├── Agent 交易表现分 (0-20)
│   ├── 7d PnL 改善 (0-8)
│   ├── 回撤评分 (0-4)
│   ├── 交易频率稳定性 (0-4)
│   └── 单笔暴赚依赖扣分 (0-4)
│
├── 排名趋势分 (0-15)
│   ├── 1h 排名上升 (0-5)
│   ├── 24h 排名上升 (0-5)
│   ├── 突破阈值加分 (0-3)
│   └── 跌出 top 10 扣分 (0-2)
│
├── Token 市场质量分 (0-15)
│   ├── 流动性评分 (0-5)
│   ├── 24h 成交量增长 (0-4)
│   ├── 滑点评分 (0-3)
│   └── 持有人分布 (0-3)
│
├── 注意力与可见度分 (0-10)
│   ├── （预留，Phase 2 用合理默认值）
│
└── 风险扣分 (0-20)
    ├── 价格暴涨扣分 (0-5)
    ├── 流动性不足扣分 (0-4)
    ├── 滑点过高扣分 (0-3)
    ├── 持有人集中扣分 (0-3)
    ├── 交易量异常扣分 (0-3)
    └── 合约异常扣分 (0-2)
```

## 详细评分规则

### 2.1 AI Council 入选概率分 (35 分)

#### 排名接近 top 10 (0-15)

```
排名 1-5:  15 分
排名 6-10: 12 分
排名 11-15: 8 分
排名 16-20: 4 分
排名 21-30: 2 分
排名 30+:   0 分
```

**数据来源：** agent_snapshots 表最新记录

#### 历史入选加分 (0-10)

```
AI Pot 历史入选次数:
  0 次:   0 分
  1 次:   4 分
  2 次:   7 分
  3 次+:  10 分
```

**数据来源：** agent_snapshots.is_selected 历史记录

#### 排名连续上升 (0-5)

```
过去 24 小时内排名持续改善（每改善 1 名 +0.5，上限 5 分）
需要至少 3 个快照点的排名趋势验证
```

**数据来源：** agent_snapshots 表 past 24h 记录比较

#### 长期稳定 top 20 (0-5)

```
过去 7 天有 >= 80% 的时间排名在 top 20 内: 5 分
过去 7 天有 >= 60% 的时间排名在 top 20 内: 3 分
过去 7 天有 >= 40% 的时间排名在 top 20 内: 1 分
不足 40%: 0 分
```

**数据来源：** agent_snapshots 表 past 7d 记录

### 2.2 Agent 交易表现分 (20 分)

#### 7d PnL 改善 (0-8)

```
比较当前 7d PnL 与 24 小时前的 7d PnL:
  改善 > 20%:      8 分
  改善 10%-20%:    6 分
  改善 5%-10%:     4 分
  基本持平 (±5%):  2 分
  恶化:             0 分  （且标记为负面信号）
```

**数据来源：** 比较最近两次 agent_snapshot 的 pnl_7d

#### 回撤评分 (0-4)

```
当前 max_drawdown:
  < 10%:   4 分
  10-20%:  3 分
  20-30%:  2 分
  30-50%:  1 分
  > 50%:   0 分
```

#### 交易频率稳定性 (0-4)

```
计算近 7 天每日交易次数的变异系数 (CV):
  CV < 0.3 (稳定):     4 分
  CV 0.3-0.5:          3 分
  CV 0.5-0.8:          2 分
  CV 0.8-1.0:          1 分
  CV > 1.0 (极不稳定): 0 分
```

#### 单笔暴赚依赖 (-4-0)

```
如果 max_pnl_single_trade / total_pnl_7d > 60%:
  - 暴赚 > 80%:   -4 分
  - 暴赚 > 60%:   -2 分
```

### 2.3 排名趋势分 (15 分)

#### 1h 排名上升 (0-5)

```
过去 1 小时排名改善:
  改善 >= 5 名:  5 分
  改善 3-4 名:   4 分
  改善 1-2 名:   2 分
  不变或下降:    0 分
```

#### 24h 排名上升 (0-5)

```
过去 24 小时排名改善:
  改善 >= 10 名:  5 分
  改善 5-9 名:    4 分
  改善 3-4 名:    3 分
  改善 1-2 名:    1 分
  不变或下降:     0 分
```

#### 阈值突破加分 (0-3)

```
从 20 名以外进入 15 名以内: +3 分
从 15 名以外进入 10 名以内: +2 分
```

**条件：** 需要验证前一个快照点排名在阈值外，当前在阈值内

#### 跌出扣分 (0-2)

```
从 top 10 跌出: -2 分
```

### 2.4 Token 市场质量分 (15 分)

#### 流动性评分 (0-5)

```
liquidity_usd:
  > 500K:   5 分
  200-500K: 4 分
  100-200K: 3 分
  50-100K:  2 分
  20-50K:   1 分
  < 20K:    0 分（且标记流动性风险）
```

#### 24h 成交量增长 (0-4)

```
volume_24h_change:
  > 100%:  4 分
  50-100%: 3 分
  20-50%:  2 分
  0-20%:   1 分
  下降:    0 分
```

#### 滑点评分 (0-3)

```
100 USDC 买入滑点:
  < 0.5%:  3 分
  0.5-1%:  2 分
  1-2%:    1 分
  > 2%:    0 分
```

#### 持有人分布 (0-3)

```
top_10_holder_pct:
  < 20%:   3 分（分散健康）
  20-35%:  2 分
  35-50%:  1 分
  > 50%:   0 分（集中风险）
```

### 2.5 注意力与可见度分 (10 分)

**Phase 2 注意：** 此维度在 Phase 2 使用合理默认值（0-3 分随机基础分），后续加入真实数据源后完善。

预留的评分输入：
- 论坛活跃度（帖子数/评论数）
- 交易 rationale 质量
- 社媒提及增长（Twitter/Discord）
- 社区讨论热度

### 2.6 风险扣分 (最多 -20)

#### 价格暴涨扣分 (0-5)

```
24h 价格涨幅:
  > 200%:   -5 分
  100-200%: -3 分
  50-100%:  -1 分
  < 50%:     0 分

1h 价格涨幅:
  > 60%:   额外 -2 分（且标记暴涨风险）
```

#### 流动性不足扣分 (0-4)

```
liquidity_usd < 20K:  -4 分
liquidity_usd < 50K:  -2 分
```

#### 滑点过高扣分 (0-3)

```
100 USDC 买入滑点 > 3%:   -3 分
100 USDC 买入滑点 > 2%:   -1 分
```

#### 持有人集中扣分 (0-3)

```
top_10_holder_pct > 60%:  -3 分
top_10_holder_pct > 45%:  -1 分
```

#### 交易量异常扣分 (0-3)

```
volume_24h / liquidity_usd > 5（换手率异常高）:
  且 liquidity 无对应增长:  -3 分
```

#### 合约异常扣分 (0-2)

```
条件（需外部数据判断）:
  合约未识别:       -2 分
  池子无流动性锁:   -1 分
  可暂停交易:       -1 分
```

## 推荐标签规则

| 标签 | 条件 |
|------|------|
| `hot_candidate` | score_total >= 80 且 无明显风险标签 |
| `candidate` | score_total >= 70 且 流动性基本可用 |
| `high_watch` | score_total >= 60 且 无明显风险标签 |
| `watch` | score_total >= 50 |
| `ignore` | score_total < 50 或 严重风险标记 |
| `risk_alert` | 任何单项风险扣分 >= -5 或流动性严重不足 |

## 评分引擎设计

### 继承关系

```
ScoreEngine (SignalHub)
│
├─ _determine_grade(total)    →  "A" | "B" | "C" | "D" | "E" | "F"
├─ _determine_risk_level()    →  "low" | "medium" | "high"
└─ evaluate()                 →  score, risk_level, score_flags
         │
         ▼
DegenClawScoreEngine (本项目)
│
├─ _score_council_prob()      - 入选概率评分
├─ _score_trading()           - 交易表现评分
├─ _score_rank_trend()        - 排名趋势评分
├─ _score_token_market()      - 市场质量评分
├─ _score_visibility()        - 注意力评分
└─ _calc_risk_penalty()       - 风险扣分
```

### 输入

```typescript
interface ScoringInput {
  agent: {
    id: string;
    name: string;
  };
  // 最新快照
  latestSnapshot: AgentSnapshot;
  // 历史快照（用于趋势计算）
  snapshots24h: AgentSnapshot[];
  snapshots7d: AgentSnapshot[];
  // Token 数据
  tokenMarket: TokenMarketSnapshot;
  // 历史入选记录
  selectionHistory: boolean[];
}
```

### 输出

```typescript
interface ScoringResult {
  agent_id: string;
  agent_name: string;
  token_address: string;
  
  // 总分
  score_total: number;
  
  // 各维度得分
  council_probability_score: number;
  trading_performance_score: number;
  rank_trend_score: number;
  token_market_score: number;
  visibility_score: number;
  risk_penalty: number;
  
  // 标签和推荐
  label: 'hot_candidate' | 'candidate' | 'high_watch' | 'watch' | 'ignore' | 'risk_alert';
  recommended_action: 'watch' | 'probe_buy' | 'confirm_buy' | 'hold' | 'reduce' | 'sell_or_exit' | 'block_trade';
  
  // 可解释性
  reasons: string[];          // 加分原因列表
  risk_warnings: string[];    // 风险扣分原因列表
  
  // 元数据
  scored_at: string;          // ISO datetime
  config_version: string;     // 评分配置版本
}
```

### 评分流程

```
每 1 小时:
1. ┌─ 从数据库读取所有 Agent 的最新快照
2. ├─ 对每个 Agent:
3. │  ├─ 读取 24h 快照历史
4. │  ├─ 读取 7d 快照历史
5. │  ├─ 读取对应 token 市场数据
6. │  ├─ 读取历史入选记录
7. │  ├─ 计算各维度评分
8. │  └─ 生成评分结果 + 可解释文本
9. ├─ 批量写入 agent_scores 表
10.└─ 更新推荐标签
```

## 评分配置可配置化

配置文件 `config/strategy.config.yaml` 中 scoring 部分：

```yaml
scoring:
  # 总分阈值
  min_watch_score: 60
  min_candidate_score: 70
  min_probe_buy_score: 75
  min_confirm_buy_score: 80
  
  # 各维度权重（总和 = 100）
  weights:
    council_probability: 35
    trading_performance: 20
    rank_trend: 15
    token_market: 15
    visibility: 10
  
  # 风险扣分上限
  max_risk_penalty: 20
  
  # 排名评分参数
  rank_score:
    top5: 15
    top10: 12
    top15: 8
    top20: 4
    top30: 2
    default: 0
  
  # 流动性评分阈值
  liquidity:
    excellent: 500000  # >= $500K -> 5分
    good: 200000
    fair: 100000
    poor: 50000
    min: 20000
  
  # 滑点限制
  slippage:
    max_buy_pct: 3.0
    max_sell_pct: 5.0
    score_excellent: 0.5
    score_good: 1.0
    score_fair: 2.0
  
  # 价格异常
  momentum:
    max_change_1h_pct: 60
    max_change_24h_pct: 150
    spike_penalty_1h: 2
    spike_penalty_24h: 5
  
  # 持有人集中度
  holder_concentration:
    max_pct: 60
    warning_pct: 45
```

## Scoring Worker 实现

```python
# scoring/engine.py
from scoring.score_engine import ScoreEngine  # 来自 SignalHub

class DegenClawScoreEngine(ScoreEngine):
    """继承 SignalHub 评分框架"""
    
    def evaluate_agent(self, agent: AgentData, market: MarketData) -> ScoreResult:
        dimensions = {
            "council_probability": self._council_prob(agent),
            "trading_performance": self._trading_score(agent),
            "rank_trend": self._rank_trend(agent),
            "token_market": self._token_market(market),
            "visibility": self._visibility(agent),
        }
        penalty = self._risk_penalty(agent, market)
        total = sum(dimensions.values()) + penalty
        
        return ScoreResult(
            total=max(0, total),
            dimensions=dimensions,
            risk_penalty=penalty,
            grade=self._determine_grade(total),
            label=self._to_label(total, penalty),
            reasons=self._build_reasons(dimensions, penalty),
        )
```

```python
# scheduler/scheduler.py — 定时调度
# 复用 SignalHub 的 APScheduler 管理模式
from scheduler.polling import PollingController

def run_scoring_cycle():
    engine = DegenClawScoreEngine(config)
    agents = db.get_agents_with_data()
    for agent in agents:
        result = engine.evaluate_agent(agent, agent.market)
        db.save_score(result)
    log.info(f"scored {len(agents)} agents")
```

## 验收标准

- [ ] 系统每小时自动更新评分
- [ ] 所有评分因子可通过配置文件调整
- [ ] 每个 Agent 都能看到完整的评分拆解
- [ ] 用户可以看懂为什么一个 Agent 得分高或低
- [ ] 评分记录完整保存在 agent_scores 表
- [ ] 评分结果包含 reasons 和 risk_warnings 字段
- [ ] 推荐标签逻辑正确
- [ ] 当某维度数据缺失时，评分能优雅降级（用默认值）

## 数据缺失处理策略

| 缺失数据 | 处理方式 |
|---------|---------|
| token 市场数据 | 对应维度打 0 分，标记数据缺失 |
| 24h 快照历史不足 | 使用可用数据计算，不足部分取默认值 |
| 7d 快照历史不足 | 排名趋势分降级计算 |
| holder 数据 | 持有人分布给默认分，标记缺失 |
| AI Pot 历史 | 无历史按 0 次计算 |

## 技术债务

- visibility_score 使用基础分（等待外部数据源接入后完善）
- 评分配置从 YAML 文件读取，暂不支持运行时热更新
- 评分计算为同步操作，Agent 数量超过 100 时考虑并发

## 前端更新

Phase 2 需要在 Phase 1 前端基础上新增：

1. **Agent Leaderboard 增加评分列** — 显示 score_total 和标签
2. **Agent Detail 增加评分拆解** — 雷达图或柱状图展示各维度
3. **评分趋势图** — 按时间展示 score_total 变化
4. **Agent 列表支持按评分排序** — 默认按评分降序排列

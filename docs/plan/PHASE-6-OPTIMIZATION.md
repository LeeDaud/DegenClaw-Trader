# Phase 6：策略优化与扩展

## 概述

根据真实交易和模拟交易数据优化评分模型与交易规则。Phase 6 是持续迭代阶段，没有明确的终点。

## 核心目标

1. 评分因子有效性分析
2. 事件窗口策略优化
3. 仓位模型优化
4. 退出规则优化
5. 外部数据扩展

## 详细任务拆解

### 6.1 复盘分析引擎

#### 数据源

```typescript
// 复盘分析的数据输入
interface ReviewInput {
  // 已关闭的交易
  closedTrades: ClosedTrade[];
  
  // 每个交易对应的评分历史
  scoreHistories: Map<string, ScoringResult[]>;
  
  // 每个交易对应的事件窗口
  eventWindows: Map<string, EventWindow>;
  
  // 市场整体状态（用于对照）
  marketBaseline: {
    totalMarketPnl: number;
    top10AvgPnl: number;
    top50AvgPnl: number;
  };
}
```

#### 分析维度

```typescript
interface StrategyAnalysis {
  // 总体统计
  overall: {
    totalTrades: number;
    winRate: number;
    avgPnl: number;
    avgPnlPct: number;
    totalPnl: number;
    maxDrawdown: number;
    sharpeRatio: number;
    profitFactor: number;     // 总盈利 / 总亏损
  };
  
  // 按评分区间
  byScoreRange: {
    range: string;            // "60-70" | "70-80" | "80+"
    trades: number;
    winRate: number;
    avgPnl: number;
  }[];
  
  // 按事件窗口
  byEventWindow: {
    window: string;           // "pre_selection" | ...
    trades: number;
    winRate: number;
    avgPnl: number;
  }[];
  
  // 按排名区间
  byRankRange: {
    range: string;            // "1-5" | "6-10" | "11-15" | ...
    trades: number;
    winRate: number;
    avgPnl: number;
  }[];
  
  // 按流动性区间
  byLiquidityRange: {
    range: string;            // "<50K" | "50-100K" | "100-200K" | ...
    trades: number;
    winRate: number;
    avgPnl: number;
  }[];
  
  // 按持仓时长
  byHoldingPeriod: {
    range: string;            // "<6h" | "6-12h" | "12-24h" | "24-48h" | ">48h"
    trades: number;
    winRate: number;
    avgPnl: number;
  }[];
  
  // 失败原因分布
  failureReasons: {
    reason: string;           // "追高" | "流动性不足" | ...
    count: number;
    avgLoss: number;
  }[];
  
  // 信号有效性
  signalEffectiveness: {
    signalType: string;       // "probe_buy" | "confirm_buy"
    totalSignals: number;
    executedRatio: number;
    winRate: number;
  }[];
}
```

### 6.2 因子有效性分析

#### 分析方法

对每个评分因子，比较其在盈利交易和亏损交易中的表现：

```typescript
interface FactorAnalysis {
  factor: string;               // 因子名称
  weight: number;               // 当前权重
  
  // 区分度检查（盈利 vs 亏损交易中的因子值差异）
  discrimination: {
    winAvg: number;             // 盈利交易中该因子的平均值
    lossAvg: number;            // 亏损交易中该因子的平均值
    delta: number;              // 差值（越大说明因子越有效）
    significance: 'high' | 'medium' | 'low' | 'negative';
  };
  
  // 相关性
  correlation: {
    withPnl: number;            // 与该笔交易 PnL 的相关性
    withWinRate: number;        // 与胜率的相关性
  };
  
  // 建议
  suggestion: 'increase_weight' | 'decrease_weight' | 'remove' | 'keep';
  reason: string;
}
```

#### 自动调参建议

```typescript
function suggestParameterChanges(analysis: StrategyAnalysis, currentConfig: ScoringConfig): ParameterChange[] {
  const changes: ParameterChange[] = [];
  
  // 如果某个评分区间表现特别差，建议降低该区间推荐等级
  for (const range of analysis.byScoreRange) {
    if (range.trades >= 5 && range.winRate < 0.3) {
      changes.push({
        target: `score_weight_${range.range}`,
        current: currentConfig.weights,
        suggested: 'review',
        reason: `${range.range} 区间胜率仅 ${(range.winRate * 100).toFixed(0)}%`,
      });
    }
  }
  
  // 如果某个事件窗口表现特别差，建议缩小窗口仓位
  for (const window of analysis.byEventWindow) {
    if (window.trades >= 3 && window.winRate < 0.25) {
      changes.push({
        target: `event_window_${window.window}_position_multiplier`,
        current: currentConfig.eventWindows[window.window]?.positionMultiplier,
        suggested: 'decrease',
        reason: `${window.window} 窗口胜率仅 ${(window.winRate * 100).toFixed(0)}%`,
      });
    }
  }
  
  // 如果某个流动性区间全是亏损，建议提高流动性门槛
  for (const range of analysis.byLiquidityRange) {
    if (range.trades >= 3 && range.winRate === 0) {
      changes.push({
        target: 'min_liquidity_usd',
        current: currentConfig.liquidity.minLiquidityUsd,
        suggested: 'increase',
        reason: `流动性 < ${range.range} 的交易全部亏损`,
      });
    }
  }
  
  return changes;
}
```

### 6.3 外部数据扩展

#### 社媒热度数据

```typescript
// collector-worker/src/collectors/social-collector.ts
interface SocialCollector {
  name: 'social';
  
  // 获取 Twitter/X 提及数据
  fetchTwitterMentions(agentName: string): Promise<{
    mention_count_24h: number;
    mention_change_24h: number;
    sentiment: 'positive' | 'neutral' | 'negative';
    top_tweets: string[];       // 高互动推文
  }>;
  
  // 获取 Discord 讨论热度
  fetchDiscordActivity(agentName: string): Promise<{
    message_count_24h: number;
    active_users: number;
  }>;
}

// 将社媒数据接入注意力与可见度评分
async function calculateVisibilityScore(socialData: SocialData): number {
  let score = 0;
  
  // Twitter 提及（0-4）
  if (socialData.twitter.mention_count_24h > 100) score += 4;
  else if (socialData.twitter.mention_count_24h > 50) score += 3;
  else if (socialData.twitter.mention_count_24h > 20) score += 2;
  else if (socialData.twitter.mention_count_24h > 5) score += 1;
  
  // 提及增长趋势（0-3）
  if (socialData.twitter.mention_change_24h > 100) score += 3;
  else if (socialData.twitter.mention_change_24h > 50) score += 2;
  else if (socialData.twitter.mention_change_24h > 10) score += 1;
  
  // Discord 活跃度（0-3）
  if (socialData.discord.message_count_24h > 200) score += 3;
  else if (socialData.discord.message_count_24h > 100) score += 2;
  else if (socialData.discord.message_count_24h > 50) score += 1;
  
  return Math.min(score, 10);  // 上限 10 分
}
```

#### AI Council 偏好分析

```typescript
interface CouncilPreferenceAnalyzer {
  // 分析历史上 AI Council 选中 Agent 的共性
  analyzeHistoricalSelections(): Promise<CouncilPreference>;
  
  // 预测当前候选 Agent 的入选概率
  predictSelectionProbability(agent: AgentProfile, preference: CouncilPreference): number;
}

interface CouncilPreference {
  // 排名偏好
  avgSelectedRank: number;
  rankRange: [number, number];
  
  // 表现偏好
  preferredPnlRange: [number, number];
  preferredWinRate: number;
  preferredTradeFrequency: 'high' | 'medium' | 'low';
  
  // 策略类型偏好（如果可以分类）
  strategyTypePreference?: string[];
  
  // 历史命中率
  selectionRate: number;       // 被考虑进入候选的比率
  finalSelectionRate: number;  // 最终被选中的比率
}
```

#### LLM 辅助复盘

```typescript
// review-worker/src/llm-review.ts
// LLM 角色限制：仅用于复盘解释和异常分析，不直接参与决策

import { Anthropic } from '@anthropic-ai/sdk';

interface LLMReviewInput {
  trade: ClosedTrade;
  marketContext: MarketSnapshot[];
  agentPerformance: AgentSnapshot[];
}

interface LLMReviewOutput {
  // 交易质量评估
  execution_quality: 'good' | 'fair' | 'poor';
  decision_quality: 'good' | 'fair' | 'poor';
  
  // 异常检测
  anomalies: string[];
  
  // 改进建议
  suggestions: string[];
  
  // 市场环境评估
  market_context: string;
}

async function generateLLMReview(input: LLMReviewInput): Promise<LLMReviewOutput> {
  const client = new Anthropic({
    apiKey: process.env.ANTHROPIC_API_KEY,
  });
  
  const response = await client.messages.create({
    model: 'claude-sonnet-4-6',
    max_tokens: 1000,
    messages: [{
      role: 'user',
      content: `Analyze this trade:
        - Agent: ${input.trade.agent_name}
        - Entry: $${input.trade.entry_price} at ${input.trade.entered_at}
        - Exit: $${input.trade.exit_price} at ${input.trade.exited_at}
        - PnL: ${input.trade.pnl_pct}%
        - Reason: ${input.trade.entry_reason}
        - Exit Reason: ${input.trade.exit_reason}
        
        Evaluate decision quality, execution quality, and suggest improvements.
        Consider market context from the provided snapshots.`,
    }],
  });
  
  return parseLLMResponse(response.content[0].text);
}
```

### 6.4 通知系统

#### 通知渠道

```typescript
interface Notifier {
  readonly channel: 'telegram' | 'discord' | 'email' | 'server_chan';
  
  send(message: NotificationMessage): Promise<boolean>;
}

interface NotificationMessage {
  type: NotificationType;
  title: string;
  body: string;
  severity: 'info' | 'warning' | 'critical';
  metadata?: Record<string, unknown>;
}

type NotificationType = 
  | 'high_score_agent'        // 高分 Agent 出现
  | 'probe_buy_signal'        // 生成 probe_buy
  | 'confirm_buy_signal'      // 生成 confirm_buy
  | 'order_executed'          // 交易执行成功
  | 'order_failed'            // 交易执行失败
  | 'stop_loss_triggered'     // 止损触发
  | 'take_profit_triggered'   // 止盈触发
  | 'risk_control_stop'       // 风控停机
  | 'collection_failed'       // 数据采集失败
  | 'system_error';           // 系统异常
```

#### Telegram Notifier 示例

```typescript
class TelegramNotifier implements Notifier {
  readonly channel = 'telegram';
  
  private botToken: string;
  private chatId: string;
  
  constructor() {
    this.botToken = process.env.TELEGRAM_BOT_TOKEN!;
    this.chatId = process.env.TELEGRAM_CHAT_ID!;
  }
  
  async send(message: NotificationMessage): Promise<boolean> {
    const text = this.formatMessage(message);
    
    const response = await fetch(
      `https://api.telegram.org/bot${this.botToken}/sendMessage`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: this.chatId,
          text,
          parse_mode: 'HTML',
          disable_notification: message.severity === 'info',
        }),
      }
    );
    
    return response.ok;
  }
  
  private formatMessage(msg: NotificationMessage): string {
    const emoji = {
      info: 'ℹ️',
      warning: '⚠️',
      critical: '🚨',
    };
    
    return `<b>${emoji[msg.severity]} ${msg.title}</b>\n\n${msg.body}`;
  }
}
```

### 6.5 策略周报

```typescript
// review-worker/src/weekly-report.ts
interface WeeklyReport {
  period: {
    start: string;    // 周一 00:00
    end: string;      // 周日 23:59
  };
  
  summary: {
    totalTrades: number;
    winRate: number;
    totalPnl: number;
    totalPnlPct: number;
    avgHoldingHours: number;
  };
  
  performance: {
    bestTrade: TradeResult;
    worstTrade: TradeResult;
    byDay: DaySummary[];
    byWindow: WindowSummary[];
  };
  
  risk: {
    maxDrawdown: number;
    maxDailyLoss: number;
    consecutiveLosses: number;
    stopLossTriggered: number;
    takeProfitTriggered: number;
  };
  
  recommendations: string[];
}

async function generateWeeklyReport(): Promise<WeeklyReport> {
  const weekStart = getPreviousMonday();
  const weekEnd = new Date();
  
  const trades = await getTradesBetween(weekStart, weekEnd);
  const analysis = analyzeTrades(trades);
  
  return {
    period: { start: weekStart.toISOString(), end: weekEnd.toISOString() },
    summary: {
      totalTrades: trades.length,
      winRate: analysis.winRate,
      totalPnl: analysis.totalPnl,
      totalPnlPct: analysis.totalPnlPct,
      avgHoldingHours: analysis.avgHoldingHours,
    },
    performance: {
      bestTrade: analysis.bestTrade,
      worstTrade: analysis.worstTrade,
      byDay: analysis.byDay,
      byWindow: analysis.byWindow,
    },
    risk: {
      maxDrawdown: analysis.maxDrawdown,
      maxDailyLoss: analysis.maxDailyLoss,
      consecutiveLosses: analysis.consecutiveLosses,
      stopLossTriggered: analysis.stopLossTriggered,
      takeProfitTriggered: analysis.takeProfitTriggered,
    },
    recommendations: generateRecommendations(analysis),
  };
}
```

### 6.6 扩展方向

| 扩展 | 优先级 | 说明 |
|------|--------|------|
| 社媒热度数据 | P0 | 增强 visibility_score 的准确性 |
| AI Council 偏好推断 | P0 | 提高入选概率评分精度 |
| LLM 自动复盘 | P1 | 辅助理解交易失败原因 |
| Telegram/Discord 通知 | P1 | 及时获知交易和异常 |
| 多钱包管理 | P2 | 分散风险和策略隔离 |
| Virtuals Agent 生命周期分析 | P2 | 覆盖更完整的 Agent 生命周期 |
| 自动调参 | P2 | 根据复盘数据自动调整评分权重 |
| 市场整体状态调整 | P2 | 牛熊市切换不同策略参数 |
| 更多 DEX 数据源 | P2 | 提升价格和流动性数据精度 |
| 链上数据分析 | P3 | 聪明钱追踪、筹码分析 |

### 6.7 配置优化

```yaml
optimization:
  # 自动调参
  auto_parameter_tuning:
    enabled: false                # 默认关闭，先手动 review
    min_trades_for_analysis: 20   # 至少 20 笔交易才分析
    adjustment_cooldown_days: 7   # 两次调参至少间隔 7 天
    
  # 复盘
  review:
    generate_weekly_report: true
    llm_review_enabled: false     # 默认不使用 LLM
    
  # 通知
  notifications:
    telegram:
      enabled: false
      bot_token_from_env: "TELEGRAM_BOT_TOKEN"
      chat_id_from_env: "TELEGRAM_CHAT_ID"
    discord:
      enabled: false
    on_events:
      - high_score_agent
      - probe_buy_signal
      - confirm_buy_signal
      - order_executed
      - order_failed
      - risk_control_stop
      - collection_failed
      - system_error
```

## 验收标准

- [ ] 系统能输出策略周报
- [ ] 系统能识别高胜率信号类型
- [ ] 系统能自动降低无效信号权重
- [ ] 系统能形成可持续迭代的数据闭环
- [ ] 每个评分因子的有效性可量化
- [ ] 复盘数据能指导配置调整

## 持续优化

Phase 6 不是一次性交付，而是持续迭代流程：

```
复盘分析 → 发现低效因子 → 调整评分配置 → 观察效果 → 再次复盘
    ↑                                               │
    └───────────────────────────────────────────────┘
```

建议的优化周期：
- 每周：策略周报 review
- 每两周：评分因子调整
- 每月：全面策略评估
- 每季度：重大策略更新

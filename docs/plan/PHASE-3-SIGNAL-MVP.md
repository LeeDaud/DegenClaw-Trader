# Phase 3：交易信号 MVP

## 概述

系统不直接交易，只生成交易信号和模拟交易计划（paper trading）。Phase 3 是整个系统的决策核心。

## 核心目标

1. 实现 Trading Decision Engine（交易决策引擎）
2. 实现 Event Window Manager（事件窗口管理器）
3. 实现 Paper Trading（模拟交易）
4. 信号列表与模拟持仓前端展示

## 核心模块

### 3.1 Event Window Manager

根据 DegenClaw 周期切换不同交易模式。

#### 时间窗口定义

```
Monday ─── Tuesday ─── Wednesday ─── Thursday ─── Friday ─── Saturday ─── Sunday
  │          │            │             │           │            │           │
  │ AI Pot   │ AI Pot     │             │           │            │           │
  │公布结果   │开始复制    │             │           │            │           │
  │          │            │             │           │            │           │
```

**窗口类型：**

| 窗口 | 时间 | 策略倾向 |
|------|------|---------|
| pre_selection | 周一前 3 天 | 布局预期，允许 probe_buy |
| result_confirmation | 周一公布日 | 确认结果，谨慎操作 |
| copy_trading | 周二开始后 3 天 | 观察 AI Pot 表现，可加仓 |
| pot_performance | 周期中段 | 持仓观察，依据表现调整 |
| risk_exit | 周期结束前 3 天 | 逐步减仓或退出 |

#### 窗口切换逻辑

```typescript
interface EventWindow {
  window: 'pre_selection' 
        | 'result_confirmation' 
        | 'copy_trading' 
        | 'pot_performance' 
        | 'risk_exit';
  
  risk_level: 'low' | 'medium' | 'high';
  
  // 此窗口允许的交易动作
  allowed_actions: ('watch' | 'probe_buy' | 'confirm_buy' | 'hold' | 'reduce' | 'sell_or_exit')[];
  
  // 仓位乘数（相对标准仓位的比例）
  position_multiplier: number;
}
```

**各窗口配置：**

```yaml
event_windows:
  pre_selection:
    risk_level: medium
    allowed_actions: ["watch", "probe_buy", "hold"]
    position_multiplier: 0.7
  
  result_confirmation:
    risk_level: medium
    allowed_actions: ["watch", "probe_buy", "hold"]
    position_multiplier: 0.5
  
  copy_trading:
    risk_level: low
    allowed_actions: ["watch", "probe_buy", "confirm_buy", "hold"]
    position_multiplier: 1.0
  
  pot_performance:
    risk_level: low
    allowed_actions: ["watch", "hold", "reduce", "sell_or_exit"]
    position_multiplier: 1.0
  
  risk_exit:
    risk_level: high
    allowed_actions: ["watch", "reduce", "sell_or_exit"]
    position_multiplier: 0.3
```

### 3.2 Trading Decision Engine

#### 决策逻辑

```typescript
function decide(input: DecisionInput): TradeSignal {
  const eventWindow = getEventWindow(input.currentDate);
  
  // Step 1: 总分过低 → 只观察
  if (input.score_total < 60) {
    return { action: 'watch', reason: '总分低于 60，仅观察' };
  }
  
  // Step 2: 总分合格 → watchlist
  if (input.score_total >= 70 && input.liquidity_ok) {
    // watchlist 加入逻辑
  }
  
  // Step 3: probe_buy 条件检查
  if (input.score_total >= 75 &&
      input.rank >= 11 && input.rank <= 25 &&
      input.rank_trend === 'rising' &&
      input.volume_growth_24h > 0 &&
      input.buy_slippage_ok &&
      !input.extreme_price_spike) {
    
    // 确认事件窗口是否允许
    if (eventWindow.allowed_actions.includes('probe_buy')) {
      return { action: 'probe_buy', ... };
    }
  }
  
  // Step 4: confirm_buy 条件检查
  if (input.score_total >= 80 &&
      input.rank_consistently_rising &&
      input.momentum_confirmed &&
      input.liquidity_ok &&
      input.slippage_low &&
      eventWindow.allowed_actions.includes('confirm_buy')) {
    return { action: 'confirm_buy', ... };
  }
  
  // Step 5: 已持仓的退出检查
  if (input.has_position) {
    if (input.score_dropped_below_threshold || 
        input.rank_deteriorated ||
        input.liquidity_dropped ||
        input.ai_pot_cycle_ending) {
      return { action: 'reduce', ... };
    }
    
    if (input.stop_loss_triggered ||
        input.take_profit_triggered ||
        input.time_exit_triggered) {
      return { action: 'sell_or_exit', ... };
    }
  }
  
  // 默认
  return { action: 'watch', reason: '条件不足' };
}
```

#### 决策输入

```typescript
interface DecisionInput {
  // 评分数据
  score_total: number;
  score_breakdown: ScoringResult;
  
  // Agent 状态
  agent_id: string;
  agent_name: string;
  rank: number;
  rank_change_1h: number;
  rank_change_24h: number;
  rank_trend: 'rising' | 'stable' | 'falling';
  rank_consistently_rising: boolean;
  
  // Token 市场
  price_usd: number;
  liquidity_usd: number;
  volume_24h: number;
  volume_growth_24h: number; // 百分比
  buy_slippage_pct: number;
  
  // 风控检查
  liquidity_ok: boolean;
  buy_slippage_ok: boolean;
  holder_concentration_ok: boolean;
  extreme_price_spike: boolean;
  momentum_confirmed: boolean;
  slippage_low: boolean;
  
  // 持仓状态
  has_position: boolean;
  score_dropped_below_threshold: boolean;
  rank_deteriorated: boolean;
  liquidity_dropped: boolean;
  
  // 退出条件
  stop_loss_triggered: boolean;
  take_profit_triggered: boolean;
  time_exit_triggered: boolean;
  ai_pot_cycle_ending: boolean;
  
  // 事件窗口
  current_date: Date;
}
```

#### 交易信号输出

```typescript
interface TradeSignal {
  signal_id: string;          // 唯一 ID，格式: signal_YYYYMMDD_HHMMSS_XXX
  agent_id: string;
  token_address: string;
  symbol: string;
  
  action: 'watch' | 'probe_buy' | 'confirm_buy' | 'hold' | 'reduce' | 'sell_or_exit' | 'block_trade';
  confidence: 'low' | 'medium' | 'high';
  
  // 交易参数
  max_position_usdc: number;
  slippage_limit_pct: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  time_exit_hours: number;
  
  // 理由
  reason: string;
  key_factors: string[];
  
  // 风控检查结果
  risk_checks: {
    liquidity_ok: boolean;
    spread_ok: boolean;
    holder_concentration_ok: boolean;
    daily_loss_limit_ok: boolean;
    event_window_ok: boolean;
    [key: string]: boolean;
  };
  
  // 状态
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'expired';
  
  // 元数据
  window: string;
  created_at: string;
  expires_at: string;
}
```

### 3.3 交易参数计算

当信号为 `probe_buy` 或 `confirm_buy` 时，自动计算以下参数：

#### 仓位大小

```typescript
function calculatePosition(input: DecisionInput, config: StrategyConfig): number {
  // 基础仓位 = 总资金 * max_single_trade_pct
  let basePosition = totalCapital * config.strategy.max_single_trade_pct / 100;
  
  // probe_buy 用 20-30% 仓位
  if (action === 'probe_buy') {
    basePosition *= 0.25;
  }
  
  // 事件窗口调节
  basePosition *= eventWindow.position_multiplier;
  
  // 评分调节 (75-100 -> 0.5x-1.5x)
  const scoreMultiplier = 0.5 + (input.score_total - 75) / 50;
  basePosition *= Math.min(scoreMultiplier, 1.5);
  
  // 流动性限制 (仓位不能超过流动性的 5%)
  const liquidityCap = input.liquidity_usd * 0.05;
  
  return Math.min(basePosition, liquidityCap);
}
```

#### 止损止盈

```typescript
function calculateExitParams(action: string): {
  stop_loss_pct: number;
  take_profit_pct: number;
  time_exit_hours: number;
} {
  if (action === 'probe_buy') {
    return { stop_loss_pct: 12, take_profit_pct: 35, time_exit_hours: 36 };
  }
  if (action === 'confirm_buy') {
    return { stop_loss_pct: 10, take_profit_pct: 40, time_exit_hours: 72 };
  }
  // 默认
  return { stop_loss_pct: 15, take_profit_pct: 30, time_exit_hours: 48 };
}
```

### 3.4 Paper Trading 模块

#### 执行流程

```
Signal Worker 每 15 分钟运行
    │
    ├── 读取最新评分结果
    ├── 判断当前事件窗口
    ├── 对每个 Agent 调用 Trading Decision Engine
    ├── 生成交易信号（保存到 trade_signals）
    │
    └── Paper Trading 模块（事件驱动，信号生成后触发）
         │
         ├── probe_buy / confirm_buy:
         │   ├── 创建 paper position
         │   ├── 记录买入价格（模拟）
         │   └── 更新 signal 状态为 executed
         │
         ├── sell_or_exit / reduce:
         │   ├── 查找对应 paper position
         │   ├── 计算模拟盈亏
         │   ├── 关闭或减少仓位
         │   └── 触发复盘生成
         │
         └── watch / hold:
             └── 仅记录，不模拟交易
```

#### Paper Position 模拟

```typescript
interface PaperPosition {
  id: string;
  signal_id: string;
  token_address: string;
  agent_id: string;
  
  // 模拟买入
  simulated_entry_price: number;
  simulated_amount_token: number;
  simulated_cost_usdc: number;
  simulated_slippage: number;    // 模拟滑点（基于当时的滑点数据 + 随机因子）
  entered_at: string;
  
  // 当前状态
  current_price: number;
  unrealized_pnl: number;
  
  // 模拟退出
  simulated_exit_price?: number;
  simulated_realized_pnl?: number;
  simulated_exit_slippage?: number;
  exited_at?: string;
  exit_reason?: string;
}
```

#### 模拟滑点

```typescript
function simulateSlippage(marketSlippage: number, orderSize: number, liquidity: number): number {
  // 基础滑点 = 当时的市场滑点估算
  // 订单大小越大，滑点越大
  const sizeFactor = orderSize / liquidity;
  const baseSlippage = marketSlippage;
  
  // 加上随机因素（±30%），反映真实滑点的不确定性
  const randomFactor = 0.7 + Math.random() * 0.6; // 0.7 ~ 1.3
  
  return baseSlippage * (1 + sizeFactor) * randomFactor;
}
```

### 3.5 Signal Worker 实现

```typescript
// signal-worker/src/index.ts
import cron from 'node-cron';
import { TradingDecisionEngine } from './engine';
import { EventWindowManager } from './event-window';
import { PaperTrader } from './paper-trader';

const decisionEngine = new TradingDecisionEngine();
const eventWindowManager = new EventWindowManager();
const paperTrader = new PaperTrader();

cron.schedule('*/15 * * * *', async () => {
  // 每 15 分钟运行
  
  // 1. 读取评分结果
  const scores = await db.select().from(agentScoresTable)
    .orderBy(desc(agentScoresTable.scored_at))
    .limit(50);
  
  // 2. 判断事件窗口
  const window = eventWindowManager.getCurrentWindow();
  
  // 3. 对每个 Agent 生成信号
  for (const score of scores) {
    const input = await buildDecisionInput(score);
    const signal = decisionEngine.decide(input, window);
    
    // 保存信号
    await saveSignal(signal);
    
    // 如果是可交易信号，执行 paper trade
    if (['probe_buy', 'confirm_buy', 'sell_or_exit', 'reduce'].includes(signal.action)) {
      await paperTrader.execute(signal);
    }
  }
  
  // 4. 更新 paper position 价格
  await paperTrader.updatePrices();
  
  log.info('signal_cycle_completed', { 
    agentCount: scores.length, 
    signals: signals.length 
  });
});
```

## 新增/修改 API

```
GET /api/v1/signals
  └─ 返回交易信号列表（分页，支持按状态筛选）

GET /api/v1/signals/:id
  └─ 返回单个信号详情

GET /api/v1/positions/paper
  └─ 返回 paper trading 持仓列表

GET /api/v1/positions/paper/:id
  └─ 返回单个 paper position 详情

GET /api/v1/event-window
  └─ 返回当前事件窗口状态

GET /api/v1/performance/paper
  └─ 返回 paper trading 总体表现
```

## 前端新增页面

### Signals 页面 (`/signals`)

```
┌──────────────────────────────────────────────────────────┐
│ Filter: [All] [Pending] [Buy] [Sell]                     │
├──────────────────────────────────────────────────────────┤
│ Time       Agent  Action     Confidence  Reason         Status │
│ 12:15     AXP    probe_buy  high        Rank ↑, vol ↑  pending │
│ 12:00     BZX    watch      low         Score < 60     active  │
│ 11:45     CYX    sell_exit  medium      Liq ↓, rank ↓  executed│
└──────────────────────────────────────────────────────────┘
```

### Paper Trading Positions (`/positions`)

```
┌─────────────────────────────────────────────────────────────────┐
│ Token  Entry   Current  PnL      Stop   Target  Time Left  Status│
│ $AXP   $0.42   $0.48    +14.3%   $0.37  $0.57   22h        open  │
│ $BZX   $1.23   $1.15    -6.5%    $1.08  $1.66   48h        open  │
└─────────────────────────────────────────────────────────────────┘
```

### Paper Trading Performance (`/performance`)

```
┌──────────────────────────────────────────────┐
│ Paper Trading Summary                         │
│ Total Trades: 24    Win Rate: 62.5%           │
│ Total PnL: +$45.20  Avg PnL: +$1.88          │
├──────────────────────────────────────────────┤
│ PnL Curve (Recharts line chart)              │
├──────────────────────────────────────────────┤
│ Action Distribution │ Win Rate by Window     │
│ [Pie chart]         │ [Bar chart]            │
└──────────────────────────────────────────────┘
```

## 信号去重规则

避免在短时间内对同一个 token 生成重复信号：

```typescript
function isDuplicate(lastSignal: TradeSignal, newSignal: DecisionOutput): boolean {
  const timeSinceLastSignal = Date.now() - lastSignal.created_at.getTime();
  
  // 同一 token 同一动作，30 分钟内不重复
  if (lastSignal.token_address === newSignal.token_address &&
      lastSignal.action === newSignal.action &&
      timeSinceLastSignal < 30 * 60 * 1000) {
    return true;
  }
  
  return false;
}
```

## 验收标准

- [ ] 系统可以连续生成 30 条以上信号
- [ ] 每条信号都有明确理由（reason 字段不为空）
- [ ] 每条信号都有入场、退出和风控参数
- [ ] 模拟交易结果可以被完整复盘
- [ ] 事件窗口切换正确
- [ ] 同一 token 不会在短时间内生成重复信号
- [ ] Paper trading 正确模拟买卖和盈亏
- [ ] 前端可以查看信号列表和 paper position 详情
- [ ] 前端可以查看 paper trading 总体表现

## 技术债务

- Paper trading 使用模拟滑点，非真实链上数据
- 信号去重使用简单的时间窗口规则
- 风控模块使用基础规则（Phase 5 完善）

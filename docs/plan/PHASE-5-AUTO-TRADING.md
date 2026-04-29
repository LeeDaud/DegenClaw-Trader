# Phase 5：小资金自动交易

## 概述

在严格风控条件下开放小资金自动交易。这是系统最核心的能力——不需要用户手动确认，在条件满足时自动执行完整买卖闭环。

## 核心目标

1. 自动交易执行（仅限 hot_candidate 标签，复用 OKX-Robot executor）
2. 自动风控（复用 OKX-Robot DailyLossGuard + 扩展全局风控）
3. 自动退出（止损/止盈/时间退出全自动，复用 OKX-Robot TakeProfitMonitor）
4. 紧急停止机制
5. 资金曲线与统计

## 代码复用说明

Phase 5 直接复用 **OKX-Robot (015)** 的风控和执行模块：

| 复用模块 | 复用的具体能力 |
|---------|--------------|
| `okx-robot/src/risk/guard.py` | DailyLossGuard：日亏损追踪、午夜重置、阈值拦截、热加载 |
| `okx-robot/src/risk/take_profit.py` | TakeProfitMonitor：定期检查持仓 ROI，达阈值自动卖出 |
| `okx-robot/src/executor/trader.py` | _check_gas() Gas 检查、_validate_quote() 报价验证 |
| `okx-robot/src/db/database.py` | get_today_pnl() 日 PnL 查询、崩溃恢复 |

**复用方式：** 直接 import，在 DegenClaw RiskEngine 中组合 OKX-Robot 的 guard + 新增 Token/Event 风控。

```python
from risk.guard import DailyLossGuard          # 日亏损风控
from risk.take_profit import TakeProfitMonitor  # 止盈监控

class DegenClawRiskEngine:
    def __init__(self, config):
        self.guard = DailyLossGuard(config.daily_loss_limit)
        self.tp_monitor = TakeProfitMonitor(...)
```

详见 [REUSE-STRATEGY.md](REUSE-STRATEGY.md)。

## 核心原则

1. **风控 > 盈利**：任何风控条件不满足，交易自动拒单
2. **逐步放开**：先 paper 验证 → 小资金自动 → 逐步扩大
3. **可随时中断**：用户始终有权一键停止所有自动交易
4. **可审计**：每笔自动交易的原因、条件、结果完全可追溯

## 自动交易限制

```
┌─────────────────────────────────────────────────┐
│              自动交易的硬性限制                    │
│                                                   │
│ 只允许 hot_candidate 标签自动交易                   │
│ 单笔仓位 ≤ 总资金 2%                               │
│ 单 token 仓位 ≤ 总资金 5%                          │
│ 策略总仓位 ≤ 总资金 20%                            │
│ 日亏损 > 3% 自动停机                               │
│ 连续亏损 3 笔自动停机                              │
│ 滑点超限自动拒单                                   │
│ 买入间隔至少 10 分钟                               │
│ 单日交易次数上限 10 次                             │
└─────────────────────────────────────────────────┘
```

## 详细任务拆解

### 5.1 Risk Control Engine（独立风控模块）

#### 架构

```
        Trading Decision Engine
                │
                ▼
         ╔══════════════════╗
         ║  Risk Control   ║  ←── 全局风控(OKX) + token风控 + 事件风控
         ║  Engine         ║
         ╚══════════════════╝
                │
        ┌───────┴───────┐
        ▼               ▼
    Pass (执行)      Fail (拒单)
```

#### 复用 OKX-Robot 风控

```python
# risk/engine.py
import sys
sys.path.append(env('OKXROBOT_PATH'))

from risk.guard import DailyLossGuard  # 直接从 OKX-Robot 引用

class DegenClawRiskEngine:
    """在 OKX-Robot 风控基础上扩展"""
    
    def __init__(self, config: RiskConfig):
        # 复用 OKX-Robot 的日亏损风控
        self.daily_loss_guard = DailyLossGuard(config.daily_loss_limit_usd)
        
        # 新增 DegenClaw 专用风控
        self.token_risk = TokenRiskChecker(config)
        self.event_risk = EventRiskChecker(config)
    
    async def check_all(self, signal: TradeSignal) -> RiskCheckResult:
        # 全局风控（复用 OKX-Robot）
        if not self.daily_loss_guard.can_trade():
            return RiskCheckResult.fail("daily_loss_limit")
        
        # Token 风控（新增）
        if not await self.token_risk.check(signal.token_address):
            return RiskCheckResult.fail("token_risk")
        
        # 事件风控（新增）
        if not await self.event_risk.check(signal):
            return RiskCheckResult.fail("event_risk")
        
        return RiskCheckResult.pass_()
```

#### 风控类型

**全局风控（Global Risk）**

```typescript
interface GlobalRiskCheck {
  type: 'global';
  
  // 日亏损检查
  daily_loss: {
    current_loss: number;       // USDC
    max_loss: number;           // 总资金 * daily_loss_limit_pct
    passed: boolean;
  };
  
  // 连续亏损检查
  consecutive_losses: {
    current_count: number;
    max_count: number;           // 配置中定义
    passed: boolean;
  };
  
  // 交易频率检查
  trade_frequency: {
    today_trades: number;
    max_trades: number;          // 配置中定义
    passed: boolean;
  };
  
  // 交易间隔检查
  cooldown: {
    last_trade_at: Date;
    min_interval_ms: number;     // 配置中定义
    passed: boolean;
  };
  
  // 总敞口检查
  total_exposure: {
    current_pct: number;
    max_pct: number;             // 配置中定义
    passed: boolean;
  };
}
```

**Token 风控（Token Risk）**

```typescript
interface TokenRiskCheck {
  type: 'token';
  token_address: string;
  
  // 流动性检查
  liquidity: {
    current_usd: number;
    min_usd: number;
    passed: boolean;
  };
  
  // 买入滑点检查
  buy_slippage: {
    current_pct: number;
    max_pct: number;
    passed: boolean;
  };
  
  // 卖出滑点检查
  sell_slippage: {
    current_pct: number;
    max_pct: number;
    passed: boolean;
  };
  
  // 价格异常检查
  price_spike_24h: {
    change_pct: number;
    max_pct: number;
    passed: boolean;
  };
  
  // 价格异常检查（1h）
  price_spike_1h: {
    change_pct: number;
    max_pct: number;
    passed: boolean;
  };
  
  // 持有人集中度检查
  holder_concentration: {
    top10_pct: number;
    max_pct: number;
    passed: boolean;
  };
}
```

**事件风控（Event Risk）**

```typescript
interface EventRiskCheck {
  type: 'event';
  
  // 事件窗口检查
  event_window: {
    current: string;
    allowed_actions: string[];
    action: string;
    passed: boolean;
  };
  
  // AI Council 后价格检查
  post_announcement: {
    price_change_since_announcement: number;
    max_allowed_change: number;
    passed: boolean;
  };
  
  // AI Pot 周期结束检查
  pot_cycle_ending: {
    days_until_end: number;
    action_required: boolean;
  };
}
```

#### 风控整体结果

```typescript
interface RiskCheckResult {
  passed: boolean;        // 所有检查必须通过
  global: GlobalRiskCheck;
  token?: TokenRiskCheck;
  event?: EventRiskCheck;
  
  // 拒绝原因（如果 passed = false）
  rejection_reason?: string;
  
  // 建议动作（风控视角）
  suggested_action?: 'block' | 'warn' | 'allow';
  
  checked_at: string;
}
```

#### 风控执行流程

```typescript
async function executeRiskCheck(signal: TradeSignal): Promise<RiskCheckResult> {
  // 1. 全局风控（优先级最高）
  const globalCheck = await checkGlobalRisk();
  if (!globalCheck.passed) {
    return {
      passed: false,
      global: globalCheck,
      rejection_reason: `全局风控未通过: ${getFailedCheckReason(globalCheck)}`,
      checked_at: new Date().toISOString(),
    };
  }
  
  // 2. Token 风控
  const tokenCheck = await checkTokenRisk(signal.token_address);
  if (!tokenCheck.passed) {
    return {
      passed: false,
      global: globalCheck,
      token: tokenCheck,
      rejection_reason: `Token 风控未通过: ${getFailedCheckReason(tokenCheck)}`,
      checked_at: new Date().toISOString(),
    };
  }
  
  // 3. 事件风控
  const eventCheck = await checkEventRisk(signal);
  if (!eventCheck.passed) {
    return {
      passed: false,
      global: globalCheck,
      token: tokenCheck,
      event: eventCheck,
      rejection_reason: `事件风控未通过: ${getFailedCheckReason(eventCheck)}`,
      checked_at: new Date().toISOString(),
    };
  }
  
  // 全部通过
  return {
    passed: true,
    global: globalCheck,
    token: tokenCheck,
    event: eventCheck,
    checked_at: new Date().toISOString(),
  };
}
```

### 5.2 自动执行流程

```
Signal Worker 生成信号
    │
    ├── 检查标签: 只有 hot_candidate 可自动执行
    │
    ├── Risk Control Engine 检查
    │   ├── Pass ──→ 自动提交执行
    │   └── Fail  ──→ 记录拒绝原因，更新信号状态
    │
    ├── Executor Service
    │   ├── Step 1: 生成 Order
    │   ├── Step 2: 调用 Trading Adapter
    │   └── Step 3: 记录结果
    │
    └── Position Manager
        ├── 创建持仓记录
        └── 启动自动监控
```

#### 自动交易条件检查（完整版）

```typescript
function canAutoExecute(signal: TradeSignal, config: StrategyConfig): boolean {
  // 1. 全局开关
  if (!config.execution.auto_trade_enabled) {
    return false;
  }
  
  // 2. 只允许 hot_candidate
  if (signal.label !== 'hot_candidate') {
    return false;
  }
  
  // 3. 只允许买入动作
  if (!['probe_buy', 'confirm_buy'].includes(signal.action)) {
    return false;
  }
  
  // 4. 检查日交易次数上限
  const todayTrades = getTodayTradeCount();
  if (todayTrades >= config.strategy.max_trades_per_day) {
    log.warn('trade_limit_reached', { todayTrades });
    return false;
  }
  
  // 5. 检查冷却时间
  const lastTradeAt = getLastTradeTime();
  if (lastTradeAt && (Date.now() - lastTradeAt.getTime()) < config.strategy.cooldown_minutes * 60 * 1000) {
    log.warn('cooldown_active', { lastTradeAt });
    return false;
  }
  
  return true;
}
```

### 5.3 Position Worker（自动退出）

每 1 分钟运行一次的持仓监控 worker，新增自动退出能力。止盈监控直接使用 OKX-Robot 的 `TakeProfitMonitor`：

```python
# position/manager.py
import sys
sys.path.append(env('OKXROBOT_PATH'))

from risk.take_profit import TakeProfitMonitor  # 复用 OKX-Robot 止盈监控

class DegenClawPositionManager:
    """持仓管理，复用 OKX-Robot TakeProfitMonitor + 新增退出条件"""
    
    def __init__(self, config):
        self.tp_monitor = TakeProfitMonitor(
            trader=self.executor.trader,
            interval=config.take_profit_check_sec,  # 默认 60s
            roi_threshold=config.take_profit_roi,   # 默认 0.30
        )
        # 注册退出回调（卖出后记录复盘）
        self.tp_monitor.on_take_profit = self._on_exit
    
    async def run_cycle(self):
        """每分钟执行一次"""
        positions = await db.get_open_positions()
        
        for pos in positions:
            await self._update_price(pos)
            
            # 检查退出条件（扩展 OKX-Robot 的止盈检查）
            exit_signal = await self._check_exit_conditions(pos)
            if exit_signal:
                await self._execute_exit(pos, exit_signal)
    
    async def _check_exit_conditions(self, pos: Position) -> ExitSignal | None:
        # 止损（价格条件）
        if pos.current_price <= pos.stop_loss_price:
            return ExitSignal(type="stop_loss")
        
        # 止盈（由 TakeProfitMonitor 处理，这里是补充）
        if pos.current_price >= pos.take_profit_price:
            return ExitSignal(type="take_profit")
        
        # 时间退出
        if datetime.now() >= datetime.fromisoformat(pos.time_exit_at):
            return ExitSignal(type="time_exit")
        
        # Agent 评分下降（DegenClaw 特有）
        latest_score = await db.get_latest_score(pos.agent_id)
        if latest_score and latest_score.score_total < 60:
            return ExitSignal(type="score_drop")
        
        # 排名恶化（DegenClaw 特有）
        snapshot = await db.get_latest_snapshot(pos.agent_id)
        if snapshot and snapshot.rank > 30:
            return ExitSignal(type="rank_deterioration")
        
        # 流动性恶化（DegenClaw 特有）
        market = await db.get_token_market(pos.token_address)
        if market and market.liquidity_usd < 20000:
            return ExitSignal(type="liquidity_drop")
        
        return None
```

### 5.4 自动停机机制

#### 触发条件

```typescript
interface StopTrigger {
  type: 'daily_loss' | 'consecutive_losses' | 'system_error' | 'manual' | 'config_change';
  reason: string;
  triggered_at: string;
}

async function checkStopConditions(): Promise<StopTrigger | null> {
  // 日亏损超限
  const dailyPnl = await getDailyPnl();
  const dailyLimit = totalCapital * config.strategy.daily_loss_limit_pct / 100;
  if (dailyPnl < -dailyLimit) {
    return {
      type: 'daily_loss',
      reason: `日亏损 $${Math.abs(dailyPnl).toFixed(2)} 超过限制 $${dailyLimit.toFixed(2)}`,
      triggered_at: new Date().toISOString(),
    };
  }
  
  // 连续亏损
  const recentTrades = await getRecentTrades(3);
  if (recentTrades.length === 3 && recentTrades.every(t => t.pnl < 0)) {
    return {
      type: 'consecutive_losses',
      reason: '连续 3 笔亏损',
      triggered_at: new Date().toISOString(),
    };
  }
  
  return null;
}
```

#### 停机状态管理

```typescript
interface TradingStatus {
  auto_trading_enabled: boolean;
  stopped_at?: string;
  stop_reason?: string;
  resume_available_at?: string;  // 自动恢复时间（如果是日亏损，次日自动恢复）
  manual_resume_required: boolean;
}

// 日亏损停机：次日自动恢复
async function handleDailyLossStop(trigger: StopTrigger) {
  await setTradingStatus({
    auto_trading_enabled: false,
    stopped_at: trigger.triggered_at,
    stop_reason: trigger.reason,
    resume_available_at: nextDayMidnight(),  // 次日 00:00
    manual_resume_required: false,
  });
  
  // 发送通知
  await notifyStop(trigger);
}

// 连续亏损停机：需要手动恢复
async function handleConsecutiveLossStop(trigger: StopTrigger) {
  await setTradingStatus({
    auto_trading_enabled: false,
    stopped_at: trigger.triggered_at,
    stop_reason: trigger.reason,
    manual_resume_required: true,
  });
  
  // 发送通知
  await notifyStop(trigger);
}

// 手动恢复
async function resumeAutoTrading() {
  const status = await getTradingStatus();
  if (status.auto_trading_enabled) {
    throw new Error('自动交易已在运行');
  }
  if (status.manual_resume_required && !isAdmin()) {
    throw new Error('需要管理员权限恢复');
  }
  
  await setTradingStatus({ auto_trading_enabled: true });
}
```

### 5.5 紧急停止

```typescript
// 紧急停止 API
// POST /api/v1/emergency/stop

interface EmergencyStopResult {
  stopped: boolean;
  action: 'stop_only' | 'stop_and_liquidate';
  affected_positions: number;
  messages: string[];
}

async function emergencyStop(liquidate: boolean = false): Promise<EmergencyStopResult> {
  // 1. 立即停止所有自动交易
  await setTradingStatus({
    auto_trading_enabled: false,
    stopped_at: new Date().toISOString(),
    stop_reason: 'emergency_stop',
    manual_resume_required: true,
  });
  
  const messages = ['自动交易已停止'];
  
  // 2. 可选择清仓
  if (liquidate) {
    const openPositions = await getOpenPositions();
    for (const position of openPositions) {
      const order = await createEmergencyExitOrder(position);
      await executeOrder(order);  // 紧急退出不经过完整风控
      messages.push(`已清仓 ${position.token_address}`);
    }
  }
  
  return {
    stopped: true,
    action: liquidate ? 'stop_and_liquidate' : 'stop_only',
    affected_positions: liquidate ? openPositions.length : 0,
    messages,
  };
}
```

### 5.6 新增/修改 API

```
POST /api/v1/executor/start-auto
  └─ 开启自动交易

POST /api/v1/executor/stop-auto
  └─ 关闭自动交易

GET /api/v1/trading-status
  └─ 当前交易状态

POST /api/v1/emergency/stop
  └─ 紧急停止（可附带清仓）

POST /api/v1/emergency/resume
  └─ 恢复自动交易

GET /api/v1/risk/global
  └─ 当前全局风控状态

GET /api/v1/risk/token/:address
  └─ 当前 token 风控状态

GET /api/v1/capital/curve
  └─ 资金曲线数据

GET /api/v1/capital/summary
  └─ 资金总览
```

### 5.7 前端新增页面

#### 资金曲线页面 (`/capital`)

```
┌──────────────────────────────────────────────┐
│ Capital Summary                               │
│ Total: $1,000 USDC                            │
│ Deployed: $320 USDC (32%)                     │
│ Available: $680 USDC                          │
│ Today PnL: +$12.40 (+1.24%)                  │
├──────────────────────────────────────────────┤
│ Capital Curve (Recharts area chart)          │
│  ┌──────────────────────────────────────────┐│
│  │    📈                                    ││
│  └──────────────────────────────────────────┘│
├──────────────────────────────────────────────┤
│ Drawdown: -2.1%    Peak: $1,050    Now: $1,000│
└──────────────────────────────────────────────┘
```

#### 风控状态页面 (`/risk`)

```
┌──────────────────────────────────────────────┐
│ Risk Dashboard                               │
├──────────────────────────────────────────────┤
│ Global: ✅ All checks passed                  │
│                                                │
│ Daily Loss:   -$5.00 / -$30.00 max    ✅      │
│ Cons Losses:  0 / 3 max                ✅      │
│ Total Exposure: 32% / 20% max          ✅      │
│ Trades Today:  3 / 10 max              ✅      │
│ Last Trade:    12 min ago              ✅      │
├──────────────────────────────────────────────┤
│ Auto Trading: 🟢 Running                      │
│ Started: 2026-04-01 09:00                    │
│ [Stop Auto] [Emergency Stop] [Emergency Clear]│
└──────────────────────────────────────────────┘
```

### 5.8 配置

```yaml
auto_trading:
  enabled: false                         # 默认关闭，手动开启
  allowed_labels: ["hot_candidate"]      # 只允许此标签自动交易
  
  # 仓位限制
  max_single_trade_pct: 2                # 单笔 2%
  max_token_exposure_pct: 5              # 单 token 5%
  max_total_exposure_pct: 20             # 总 20%
  
  # 亏损限制
  daily_loss_limit_pct: 3                # 日亏损 3%
  max_consecutive_losses: 3              # 连续亏损 3 笔
  consecutive_loss_action: "stop_auto"   # stop_auto | reduce_position
  
  # 频率限制
  max_trades_per_day: 10
  cooldown_minutes: 10
  
  # 恢复策略
  daily_loss_resume: "next_day"          # next_day | manual_only
  consecutive_loss_resume: "manual_only"

emergency:
  confirm_required: true                 # 紧急操作需确认
  allow_partial_liquidation: true        # 允许部分清仓
```

## 验收标准

- [ ] 系统可以小资金自动执行完整买卖闭环
- [ ] 每笔交易都有完整记录（信号 → 风控 → 订单 → 持仓 → 退出）
- [ ] 风控触发时自动停止交易
- [ ] 异常时不会重复下单
- [ ] 用户可以随时关闭自动交易
- [ ] 紧急停止功能正常工作
- [ ] 日亏损超限自动停机
- [ ] 连续亏损自动停机
- [ ] 自动止损/止盈/时间退出正确执行
- [ ] 资金曲线和风控状态页面数据准确

## 风险说明

Phase 5 是本项目风险最高的阶段。建议：

1. **初始资金不超过 500 USDC**
2. **先 paper mode 运行至少 2 周**，复盘验证策略
3. **Live mode 开启前 review 所有风控配置**
4. **开启自动交易后前 3 天密切监控**
5. **准备应急方案**（私钥备份、手动清仓能力）

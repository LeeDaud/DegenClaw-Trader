# Phase 4：半自动交易

## 概述

系统生成交易计划，用户手动确认后交给机器人执行。Phase 4 是真实交易的起点——在此之前系统完全不碰真实资金。

## 核心目标

1. 交易审批流程（用户确认/拒绝信号）
2. 机器人适配器（复用 OKX-Robot executor）
3. 订单状态管理
4. 真实持仓管理
5. 执行日志

## 代码复用说明

Phase 4 直接复用 **OKX-Robot (015)** 的交易执行模块：

| 复用模块 | 复用的具体能力 |
|---------|--------------|
| `okx-robot/src/executor/okx_client.py` | OKX DEX API 完整封装（签名、报价、swap） |
| `okx-robot/src/executor/trader.py` | 交易执行（报价验证、approve、签名、广播） |
| `okx-robot/src/db/database.py` | 订单/持仓表设计模式、崩溃恢复 |
| `okx-robot/src/config/loader.py` | YAML 热加载框架 |

**复用方式：** 通过 PYTHONPATH 直接 import，不复制代码。

```python
import sys
sys.path.append(env('OKXROBOT_PATH'))

from executor.okx_client import OKXDexClient
from executor.trader import Trader
```

详见 [REUSE-STRATEGY.md](REUSE-STRATEGY.md)。

## 安全原则

- 系统永不自动下单，所有交易必须用户手动确认
- 用户确认后，交易发送到机器人执行
- 机器人执行后，系统跟踪结果但不再自动操作
- 所有订单有唯一 ID，禁止重复执行
- 用户可随时撤销待确认订单
- 生产环境默认 paper mode，live mode 需手动开启

## 详细任务拆解

### 4.1 交易审批流程

#### 用户界面

在原有 Signals 页面上，给 `pending_approval` 状态的信号增加操作按钮：

```
┌──────────────────────────────────────────────────────────┐
│ Signal: probe_buy $AXP                                    │
│                                                          │
│ Reason: Rank 14→11, 24h vol +45%, liquidity $120K OK     │
│ Amount: 20 USDC  |  Slippage: 1.5%  |  SL: 12%  |  TP: 35%│
│                                                          │
│ [Approve]  [Reject]  [View Details]                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

#### 信号生命周期

```
Signal Generated  ──→  pending_approval
                             │
                     ┌──────┴──────┐
                     ▼             ▼
                 approved       rejected
                     │
                     ▼
              executor-service  ──→  submitted
                                     │
                               ┌─────┴─────┐
                               ▼           ▼
                           confirmed     failed
                               │
                               ▼
                            closed
```

#### 状态转换规则

```typescript
type SignalStatus = 
  | 'pending'           // 新生成，等待处理
  | 'pending_approval'  // 需要用户确认
  | 'approved'          // 用户已批准
  | 'rejected'          // 用户已拒绝
  | 'executing'         // 正在执行
  | 'executed'          // 执行成功
  | 'failed'            // 执行失败
  | 'expired'           // 超过有效期
  | 'cancelled';        // 用户取消

// 状态转换矩阵
const transitions: Record<SignalStatus, SignalStatus[]> = {
  'pending':           ['pending_approval', 'expired'],
  'pending_approval':  ['approved', 'rejected', 'expired'],
  'approved':          ['executing', 'cancelled'],
  'rejected':          [],  // 终态
  'executing':         ['executed', 'failed'],
  'executed':          ['closed'],
  'failed':            [],  // 终态
  'expired':           [],  // 终态
  'cancelled':         [],  // 终态
};
```

### 4.2 Executor Service

#### 架构

```
Signal 被批准
    │
    ▼
Executor Service
    │
    ├── Step 1: 二次风控检查
    │   ├── 重新检查流动性（数据可能已变化）
    │   ├── 重新检查价格偏离
    │   ├── 检查钱包余额
    │   ├── 检查当前持仓
    │   ├── 检查仓位上限
    │   └── 检查是否重复订单
    │
    ├── Step 2: 风控通过 → 生成 Order
    │   └── 构建交易参数
    │
    ├── Step 3: 调用 OKX-Robot Executor
    │   ├── OKXDexClient.get_quote()      # 获取实时报价
    │   ├── Trader._validate_quote()       # 复用：蜜罐/价格影响/税率检查
    │   ├── Trader._check_gas()            # 复用：Gas 价格检查
    │   ├── Trader._send_swap()            # 复用：签名 + 广播 + 崩溃恢复
    │   └── OKXDexClient 的 retry 机制    # 复用：2 次重试
    │
    └── Step 4: 更新状态
        ├── 更新订单状态
        ├── 创建/更新持仓记录
        └── 记录执行日志
```

#### 实现

```python
# executor/service.py
import sys
sys.path.append(env('OKXROBOT_PATH'))

from executor.okx_client import OKXDexClient
from executor.trader import Trader

class DegenClawExecutor:
    """打包 OKX-Robot executor，接入 DegenClaw 审批流程"""
    
    def __init__(self, config: ExecutorConfig):
        self.okx = OKXDexClient(
            api_key=config.OKX_API_KEY,
            secret_key=config.OKX_SECRET_KEY,
            passphrase=config.OKX_PASSPHRASE,
        )
        self.trader = Trader(
            okx_client=self.okx,
            wallet_address=config.WALLET_ADDRESS,
            private_key=config.PRIVATE_KEY,
        )
    
    async def execute(self, order: Order) -> ExecutionResult:
        """执行交易订单"""
        # 1. 获取报价（复用 OKX-Robot 报价查询）
        quote = await self.okx.get_quote(
            chain_index="8453",  # Base
            from_token_address=USDC if order.action == "buy" else order.token_address,
            to_token_address=order.token_address if order.action == "buy" else USDC,
            amount=str(order.amount_usdc),
            slippage=str(order.max_slippage / 100),
        )
        
        # 2. 验证报价（复用 OKX-Robot 的验证逻辑）
        self.trader._validate_quote(quote)
        
        # 3. 执行交易（复用 OKX-Robot 的签名/广播逻辑）
        result = await self.trader.execute_swap(quote)
        
        return ExecutionResult(result)
```

#### 二次风控检查

```typescript
interface PreExecutionCheck {
  check: string;
  passed: boolean;
  detail?: string;
}

async function preExecutionChecks(signal: TradeSignal, config: StrategyConfig): Promise<{
  passed: boolean;
  checks: PreExecutionCheck[];
}> {
  const checks: PreExecutionCheck[] = [];
  
  // 1. 重新获取最新 token 市场数据
  const latestMarket = await dexScreenerCollector.fetchTokenByAddress(signal.token_address);
  
  // 2. 检查当前价格与决策时价格的偏离
  const priceDeviation = Math.abs(latestMarket.price_usd - signal.entry_price) / signal.entry_price;
  checks.push({
    check: 'price_deviation',
    passed: priceDeviation < 0.05,  // 偏离不超过 5%
    detail: `决策价格: ${signal.entry_price}, 当前价格: ${latestMarket.price_usd}, 偏离: ${(priceDeviation * 100).toFixed(2)}%`
  });
  
  // 3. 检查流动性是否仍然足够
  checks.push({
    check: 'liquidity',
    passed: latestMarket.liquidity_usd >= config.liquidity.min_liquidity_usd,
    detail: `当前流动性: $${latestMarket.liquidity_usd}`
  });
  
  // 4. 检查钱包余额
  const balance = await walletAdapter.getBalance('USDC');
  checks.push({
    check: 'wallet_balance',
    passed: balance >= signal.max_position_usdc,
    detail: `USDC 余额: $${balance}, 需要: $${signal.max_position_usdc}`
  });
  
  // 5. 检查当前持仓上限
  const currentPositions = await getCurrentPositions();
  const totalExposure = currentPositions.reduce((sum, p) => sum + p.cost_usdc, 0);
  const newExposure = totalExposure + signal.max_position_usdc;
  const maxExposure = totalCapital * config.strategy.max_total_exposure_pct / 100;
  
  checks.push({
    check: 'exposure_limit',
    passed: newExposure <= maxExposure,
    detail: `当前总敞口: $${totalExposure}, 新增后: $${newExposure}, 上限: $${maxExposure}`
  });
  
  // 6. 检查单 token 敞口
  const tokenExposure = (currentPositions
    .filter(p => p.token_address === signal.token_address)
    .reduce((sum, p) => sum + p.cost_usdc, 0)) + signal.max_position_usdc;
  const maxTokenExposure = totalCapital * config.strategy.max_token_exposure_pct / 100;
  
  checks.push({
    check: 'token_exposure',
    passed: tokenExposure <= maxTokenExposure,
    detail: `Token 总敞口: $${tokenExposure}, 上限: $${maxTokenExposure}`
  });
  
  // 7. 检查是否重复订单
  const duplicateOrder = await findDuplicateOrder(signal);
  checks.push({
    check: 'duplicate_order',
    passed: !duplicateOrder,
    detail: duplicateOrder ? `重复订单: ${duplicateOrder.order_id}` : undefined
  });
  
  const passed = checks.every(c => c.passed);
  return { passed, checks };
}
```

### 4.3 执行层对接

由于直接复用 OKX-Robot 的 `OKXDexClient` 和 `Trader`，不需要额外开发 Trading Adapter。对接方式：

```python
# executor/service.py

class DegenClawExecutor:
    """直接包装 OKX-Robot 的交易能力"""
    
    async def execute_buy(self, signal: TradeSignal) -> ExecutionResult:
        # 复用 OKX-Robot 的 Trader 执行买入
        order = await self._build_order(signal, "buy")
        return await self._execute_with_risk_check(order)
    
    async def execute_sell(self, position: Position) -> ExecutionResult:
        # 复用 OKX-Robot 的 Trader 执行卖出
        order = await self._build_sell_order(position)
        return await self._execute_with_risk_check(order)
```

OKX-Robot 提供的完整能力：
- OKX DEX API 报价和 swap 交易构建
- 蜜罐检测、价格影响检查、税率检查
- Gas 价格检查
- Allowance → Approve → 签名 → 广播 全流程
- pending tx 崩溃恢复

无需实现的模块：
- ~~OKX DEX API 封装~~ → 直接用 OKXDexClient
- ~~交易签名和广播~~ → 直接用 Trader._send_swap()
- ~~报价验证~~ → 直接用 Trader._validate_quote()
- ~~交易重试~~ → 直接用 OKXDexClient 的重试逻辑

#### 配置

```yaml
execution:
  mode: paper                          # paper | live
  auto_trade_enabled: false
  
  # OKX-Robot 配置复用
  adapter:
    type: okx_robot                    # 直接引用 OKX-Robot
    path: "${OKXROBOT_PATH}"           # 从 .env 读取
    
  # OKX DEX 参数
  slippage: 0.01                       # 1% 滑点（复用 OKX-Robot 格式）
  gas_limit_gwei: 10                   # Gas 上限
  trade_retry: 2                       # 重试次数
  
  # 订单有效期
  pending_order_expiry_minutes: 60
```

### 4.4 订单状态管理

#### 订单表扩展

```typescript
interface TradeOrder {
  id: number;
  order_id: string;           // 系统生成，格式: ord_YYYYMMDD_HHMMSS_XXX
  signal_id: string;
  token_address: string;
  
  action: 'buy' | 'sell';
  amount_usdc: number;
  amount_token?: number;
  
  // 预期价格
  expected_price: number;
  
  // 实际成交
  actual_price?: number;
  slippage?: number;
  
  // 执行
  status: 'pending' | 'approved' | 'rejected' | 'submitted' | 'confirmed' | 'failed' | 'cancelled' | 'closed';
  tx_hash?: string;
  error_message?: string;
  
  // 关联
  position_id?: number;
  
  // 时间
  approved_at?: string;
  submitted_at?: string;
  confirmed_at?: string;
  failed_at?: string;
  created_at: string;
  updated_at: string;
}
```

#### 订单生命周期

```
Order Created (pending)
    │
    ▼
  approved ──→ submitted ──→ confirmed ──→ closed
                  │               │
                  ▼               ▼
              failed           failed
                  │
                  ▼
              cancelled
```

### 4.5 真实持仓管理

#### 持仓表

```typescript
interface Position {
  id: number;
  token_address: string;
  agent_id: string;
  
  // 持仓量
  amount_token: number;
  cost_usdc: number;
  entry_price: number;
  
  // 最新价格
  current_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  
  // 退出条件
  stop_loss_price: number;
  take_profit_price: number;
  time_exit_at: string;       // 时间退出 deadline
  
  // 状态
  status: 'open' | 'closing' | 'closed';
  
  // 关联信号
  entry_signal_id: string;
  exit_signal_id?: string;
  
  created_at: string;
  closed_at?: string;
}
```

#### 持仓监控

```typescript
// 在 position-worker 中每 1 分钟运行
async function monitorPositions() {
  const openPositions = await db.select().from(positionsTable)
    .where(eq(positionsTable.status, 'open'));
  
  for (const position of openPositions) {
    // 1. 更新最新价格
    const market = await dexScreenerCollector.fetchTokenByAddress(position.token_address);
    position.current_price = market.price_usd;
    position.unrealized_pnl = (position.current_price - position.entry_price) / position.entry_price * position.cost_usdc;
    
    // 2. 检查止损
    if (position.current_price <= position.stop_loss_price) {
      await triggerExit(position, 'stop_loss');
      continue;
    }
    
    // 3. 检查止盈
    if (position.current_price >= position.take_profit_price) {
      await triggerExit(position, 'take_profit');
      continue;
    }
    
    // 4. 检查时间退出
    if (new Date() >= new Date(position.time_exit_at)) {
      await triggerExit(position, 'time_exit');
      continue;
    }
    
    // 5. 更新持仓记录
    await db.update(positionsTable).set({
      current_price: position.current_price,
      unrealized_pnl: position.unrealized_pnl,
    }).where(eq(positionsTable.id, position.id));
  }
}

async function triggerExit(position: Position, reason: string) {
  // 生成卖出信号（需要用户确认）
  const exitSignal = await createExitSignal(position, reason);
  
  // 标记持仓为 closing
  await db.update(positionsTable).set({
    status: 'closing',
  }).where(eq(positionsTable.id, position.id));
}
```

### 4.6 新增 API

```
GET /api/v1/signals/pending
  └─ 待确认信号列表

POST /api/v1/signals/:id/approve
  └─ 批准信号，触发执行

POST /api/v1/signals/:id/reject
  └─ 拒绝信号

GET /api/v1/orders
  └─ 订单列表

GET /api/v1/orders/:id
  └─ 订单详情

GET /api/v1/positions
  └─ 当前持仓列表

GET /api/v1/positions/:id
  └─ 持仓详情

POST /api/v1/positions/:id/close
  └─ 手动平仓

GET /api/v1/executor/status
  └─ 执行器状态

POST /api/v1/executor/switch-mode
  └─ 切换 paper/live 模式
```

### 4.7 前端新增/修改

#### 信号确认页面（增强现有 Signals 页面）

```
┌──────────────────────────────────────────────────────────┐
│ Pending Approvals (3)                                    │
├──────────────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────────────────┐ │
│ │ $AXP · probe_buy · 20 USDC                          │ │
│ │ Reason: Rank 14→11, vol +45%                        │ │
│ │ Amount: 20 USDC | SL: 12% | TP: 35% | Time: 36h    │ │
│ │ Risk: Liq ✓ Spread ✓ Holder ✓ Window ✓              │ │
│ │ [Approve] [Reject] [Details ▸]                      │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ $BZX · sell_or_exit · Full Exit                      │ │
│ │ Reason: Liquidity dropped below threshold             │ │
│ │ Risk: Liq ✗ Spread ✓ Holder ✓ Window ✓              │ │
│ │ [Approve Exit] [Reject] [Details ▸]                  │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

#### 持仓页面

```
┌──────────────────────────────────────────────────────────────────────┐
│ Open Positions (2)                           Total: $320 USDC        │
├──────────────────────────────────────────────────────────────────────┤
│ Token  Entry   Current  PnL      PnL%    Stop   Target  Time Left   │
│ $AXP   $0.42   $0.48    +$2.80   +14.3%  $0.37  $0.57   22h    [X] │
│ $BZX   $1.23   $1.15    -$1.60   -6.5%   $1.08  $1.66   48h    [X] │
└──────────────────────────────────────────────────────────────────────┘
```

#### 执行日志页面（`/execution-logs`）

```
┌──────────────────────────────────────────────────────────┐
│ Time         Order   Token  Action  Status  Tx Hash      │
│ 12:30:15     ord_01  AXP    Buy     Confirmed 0xabc...   │
│ 12:30:22     ord_02  BZX    Sell    Failed   Insuff liq  │
└──────────────────────────────────────────────────────────┘
```

### 4.8 配置

```yaml
execution:
  mode: paper                          # paper | live
  auto_trade_enabled: false
  require_manual_confirmation: true
  
  adapter:
    name: generic_http
    paper_mode_enabled: true
    live_mode_enabled: false           # 默认 false，手动开启
  
  # 下单参数
  max_order_retries: 3
  retry_delay_ms: 5000
  
  # 订单有效期
  pending_order_expiry_minutes: 60     # 未确认的订单 1 小时后过期
  executing_order_timeout_ms: 30000    # 执行超时 30 秒
```

## 验收标准

- [ ] 用户可以手动批准交易
- [ ] 用户可以手动拒绝交易
- [ ] 机器人可以正确接收交易指令
- [ ] 交易失败时系统能记录原因
- [ ] 交易成功后系统能跟踪持仓
- [ ] 系统不会绕过用户确认自动下单
- [ ] 二次风控检查拦截不符合条件的交易
- [ ] 订单状态转换完全正确
- [ ] 持仓数据随价格变化实时更新
- [ ] 止损/止盈/时间退出能正确触发卖出信号

## 安全要求

- API key 只从环境变量读取，不写入代码
- 所有订单有唯一 order_id（UUID 或 时间戳+随机数）
- 同一 signal 不会被重复执行（通过 signal_id 去重）
- 所有执行操作记录到 execution_log
- paper/live 模式切换需要确认

## 风险说明

Phase 4 是第一个涉及真实资金的阶段。尽管需要用户手动确认，但仍需注意：

1. **用户确认前必须**：系统明确标识这是真实交易
2. **默认 paper mode**：上线初期 paper mode 运行至少 1 周
3. **Live mode 转换**：需要修改配置文件并重启服务
4. **资金规模**：建议初始资金不超过 200 USDC

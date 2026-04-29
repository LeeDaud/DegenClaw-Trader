# 代码复用详细方案

## 复用原则

1. **直接引用，不复制粘贴** — 使用 PYTHONPATH 或 git submodule 引用原项目代码
2. **扩展而非修改** — 对原项目模块做继承/包装，不改原有代码逻辑
3. **向上游贡献** — 必要的通用改动回馈给原项目
4. **版本锁定** — 子模块指向特定 commit，升级需验证

## 目录结构

```
DegenClaw-Alpha-Engine/
├── frontend/                    # React 前端（独立，不依赖两个源项目）
├── backend/
│   ├── .env.example
│   ├── requirements.txt         # 本项目的依赖 + SignalHub + OKX 路径引用
│   ├── main.py                  # FastAPI 启动入口
│   ├── api/                     # 路由（参考 SignalHub api/routes.py 模式）
│   ├── db/                      # 数据库层（参考 SignalHub db.py 模式）
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── degenclaw_collector.py  # DegenClaw leaderboard 采集
│   │   ├── market_collector.py     # Token 市场数据采集
│   │   └── signalhub_adapter.py    # SignalHub 采集器适配
│   ├── parsers/
│   │   ├── __init__.py
│   │   └── degenclaw_parser.py     # DegenClaw 响应解析
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── engine.py               # DegenClaw 评分引擎
│   │   └── config.py               # 评分规则配置（YAML）
│   ├── decision/
│   │   ├── __init__.py
│   │   ├── engine.py               # 交易决策引擎
│   │   └── event_window.py         # 事件窗口管理
│   ├── signal/
│   │   ├── __init__.py
│   │   └── generator.py            # 信号生成器
│   ├── executor/
│   │   ├── __init__.py
│   │   ├── service.py              # DegenClaw 执行编排
│   │   ├── order_builder.py        # 订单构建
│   │   └── vendor/                 # OKX-Robot 源码链接
│   ├── risk/
│   │   ├── __init__.py
│   │   ├── engine.py               # 全局风控引擎
│   │   └── vendor/                 # OKX-Robot 源码链接
│   ├── position/
│   │   ├── __init__.py
│   │   └── manager.py              # 持仓管理
│   ├── review/
│   │   ├── __init__.py
│   │   └── engine.py               # 复盘引擎
│   └── scheduler/
│       └── scheduler.py            # APScheduler 任务调度（参考 SignalHub）
├── config/
│   ├── strategy.yaml
│   └── scoring.yaml
├── docs/
├── scripts/
└── .env.example
```

## SignalHub (004) 复用细节

### 1. sources/virtuals_source.py — 扩展为 DegenClaw 采集

**原项目路径：** `D:\AAA-Project\004-SignalHub\signalhub\app\sources\virtuals_source.py`

**现有能力：**
- HTTP 轮询 Virtuals API（httpx 异步）
- 分页、重试、配置化间隔
- sample_data 离线模式
- detail_detail_refresh_limit 增量刷新

**复用方式：**

```python
# collectors/signalhub_adapter.py
# 直接导入 SignalHub 的 VirtualsSource，扩展为 DegenClaw https 采集

import sys
sys.path.append(r'D:\AAA-Project\004-SignalHub\signalhub\app')

from sources.virtuals_source import VirtualsSource

class DegenClawSource(VirtualsSource):
    """扩展 SignalHub 的 VirtualsSource 用于 DegenClaw leaderboard 采集"""
    
    async def fetch_leaderboard(self) -> list:
        # 复用父类的 HTTP 轮询机制，修改 endpoint
        # DegenClaw 特定的 API 地址和参数
        response = await self._fetch("degenclaw/leaderboard")
        return self._parse_leaderboard(response)
    
    async def fetch_agent_detail(self, agent_id: str) -> dict:
        # 获取单个 Agent 的详细信息
        response = await self._fetch(f"agents/{agent_id}")
        return self._parse_agent_detail(response)
    
    async def fetch_ai_pot_status(self) -> dict:
        # 获取 AI Pot 当前状态
        response = await self._fetch("ai-pot/current-round")
        return self._parse_pot_status(response)
```

### 2. parsers/virtuals_parser.py — 扩展 DegenClaw 解析

**原项目路径：** `D:\AAA-Project\004-SignalHub\signalhub\app\parsers\virtuals_parser.py`

**现有能力：**
- 字段提取（支持 camelCase / snake_case 自动适配）
- EVM 地址验证（`^0x[a-fA-F0-9]{40}$`）
- 多种 API 响应格式兼容

**复用方式：**

```python
# parsers/degenclaw_parser.py
from parsers.virtuals_parser import VirtualsParser

class DegenClawParser(VirtualsParser):
    """解析 DegenClaw leaderboard 响应"""
    
    def parse_leaderboard(self, raw_data: dict) -> list[AgentEntry]:
        items = self._extract_items(raw_data)
        return [self._parse_agent(item) for item in items]
    
    def _parse_agent(self, item: dict) -> AgentEntry:
        return {
            "agent_id": self._safe_str(item, "id"),
            "name": self._safe_str(item, "name"),
            "rank": self._safe_int(item, "rank"),
            "pnl_24h": self._safe_float(item, "pnl24h", "pnl_24h"),
            "pnl_7d": self._safe_float(item, "pnl7d", "pnl_7d"),
            "win_rate": self._safe_float(item, "winRate", "win_rate"),
            "max_drawdown": self._safe_float(item, "maxDrawdown", "max_drawdown"),
            "trade_count": self._safe_int(item, "tradeCount", "trade_count"),
            "token_address": self._extract_address(item, "tokenAddress", "token_address"),
        }
```

### 3. scoring/score_engine.py — 评分框架复用

**原项目路径：** `D:\AAA-Project\004-SignalHub\signalhub\app\scoring\score_engine.py`

**现有能力：**
- 8 维度加权评分模式
- 0-100 总分制
- 等级标签（A/B/C/D/E/F）
- 风险等级判定

**复用方式：**

```python
# scoring/engine.py
from scoring.score_engine import ScoreEngine

class DegenClawScoreEngine(ScoreEngine):
    """继承 SignalHub 评分框架，实现 DegenClaw 专用评分"""
    
    def __init__(self, config: ScoringConfig):
        super().__init__()
        self.config = config
    
    def score(self, agent_data: AgentData, market_data: MarketData) -> ScoringResult:
        # 使用父类的加权计算机制
        dimensions = {
            "council_probability": self._score_council_prob(agent_data),
            "trading_performance": self._score_trading(agent_data),
            "rank_trend": self._score_rank_trend(agent_data),
            "token_market": self._score_token_market(market_data),
            "visibility": self._score_visibility(agent_data),
        }
        
        risk_penalty = self._calculate_risk_penalty(agent_data, market_data)
        total = sum(dimensions.values()) + risk_penalty
        
        # 复用父类的等级判定
        grade = self._determine_grade(total)
        
        return ScoringResult(
            total=max(0, total),
            dimensions=dimensions,
            risk_penalty=risk_penalty,
            grade=grade,
            label=self._map_grade_to_label(grade),
            reasons=self._generate_reasons(dimensions, risk_penalty),
        )
```

### 4. lifecycle/lifecycle_engine.py — 事件窗口映射

**原项目路径：** `D:\AAA-Project\004-SignalHub\signalhub\app\lifecycle\lifecycle_engine.py`

**现有能力：**
- 确定性生命周期阶段判定
- 不可逆阶段推进（不会回退到更早阶段）
- 基于 status + flag + launch_time + contract_presence 的多条件判断

**映射方案：**

```
SignalHub Lifecycle         →  DegenClaw Event Window
─────────────────────────────────────────────────────
detected / info_updated     →  pre_selection
launch_announced            →  result_confirmation
launch_open / launch_live   →  copy_trading
launch_closed               →  pot_performance
token_trading / inactive    →  risk_exit
```

```python
# decision/event_window.py
from lifecycle.lifecycle_engine import LifecycleEngine

class EventWindowManager:
    """事件窗口管理器，复用 SignalHub 生命周期引擎的设计模式"""
    
    WINDOWS = {
        "pre_selection": {
            "risk_level": "medium",
            "allowed_actions": ["watch", "probe_buy"],
            "position_multiplier": 0.7,
        },
        "result_confirmation": {
            "risk_level": "medium",
            "allowed_actions": ["watch", "probe_buy"],
            "position_multiplier": 0.5,
        },
        # ...
    }
    
    def get_current_window(self, agent: AgentData) -> EventWindow:
        # 复用不可逆阶段推进逻辑
        # 基于当前日期、Agent 排名、AI Pot 状态判定
        pass
```

### 5. database/db.py — 数据库层

**原项目路径：** `D:\AAA-Project\004-SignalHub\signalhub\app\database\db.py`

**现有能力：**
- SQLite WAL 模式
- `ON CONFLICT` upsert
- JSON 字段存储
- 模块化表设计
- 增量列迁移

**复用方式：** 直接参考 `db.py` 的模式设计 DegenClaw 的数据库层，继承基础连接管理逻辑。

### 6. explorer/basescan_trace.py + subscriptions/chainstack_launch_monitor.py

**原项目路径：**
- `D:\AAA-Project\004-SignalHub\signalhub\app\explorer\basescan_trace.py`
- `D:\AAA-Project\004-SignalHub\signalhub\app\subscriptions\chainstack_launch_monitor.py`

**复用场景：** 用于获取 token holder 分布、pool 地址、链上交易追踪。

## OKX-Robot (015) 复用细节

### 1. executor/okx_client.py — OKX DEX API 封装

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\executor\okx_client.py`

**现有能力：**
- OKX v6 DEX Aggregator API 完整封装
- HMAC-SHA256 签名
- 报价查询（`/quote`）
- 交易构建（`/swap`）
- 重试逻辑（2 次重试，1s 延迟）

**复用方式：**

```python
# executor/vendor/okx_client.py -> 直接符号链接或 PATH 引用
# 不修改原文件，直接 import

import sys
sys.path.append(r'D:\AAA-Project\015-OKX-Robot\src')
from executor.okx_client import OKXDexClient

# DegenClaw 的执行器直接使用 OKXDexClient

class DegenClawExecutor:
    def __init__(self, okx_client: OKXDexClient, config: ExecutorConfig):
        self.okx = okx_client
        self.config = config
    
    async def execute_buy(self, order: BuyOrder) -> ExecutionResult:
        # 获取报价
        quote = await self.okx.get_quote(
            from_token=USDC_ADDRESS,
            to_token=order.token_address,
            amount=str(order.amount_usdc),
        )
        # ... 使用 OKX-Robot 的 validate_quote 逻辑
        # ... 构建交易、签名、广播
        pass
    
    async def execute_sell(self, order: SellOrder) -> ExecutionResult:
        # 类似流程，方向相反
        pass
```

### 2. executor/trader.py — 交易执行

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\executor\trader.py`

**复用的核心能力：**
- `_validate_quote()` 报价安全性验证：
  - 蜜罐检测（`isHoneyPot`）
  - 价格影响检查（`< 5%`）
  - Token 税率检查（`< 5%`）
- `_send_swap()` 交易广播流程：
  - Allowance 检查 → Approve → 构建 tx → 签名 → 广播
  - Gas 价格检查（`_check_gas()`）
  - Gas limit 1.2x 倍率
  - EIP-1559 适配
- `sell()` 卖出流程
- `_calculate_amount()` 数量计算

### 3. risk/guard.py — 日亏损风控

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\risk\guard.py`

**现有能力：**
- 日亏损累计追踪（从 DB 加载历史）
- 午夜自动重置
- 阈值触发拦截
- 热加载阈值更新

**复用方式：**

```python
# risk/engine.py
from risk.guard import DailyLossGuard

class DegenClawRiskEngine:
    """在 DailyLossGuard 基础上扩展全局风控"""
    
    def __init__(self, config: RiskConfig):
        self.daily_loss_guard = DailyLossGuard(config.daily_loss_limit)
        self.token_risk = TokenRiskChecker(config)
        self.event_risk = EventRiskChecker(config)
    
    async def check(self, signal: TradeSignal) -> RiskCheckResult:
        # 全局风控
        if not self.daily_loss_guard.can_trade():
            return FAIL_DAILY_LOSS_LIMIT
        
        # Token 风控
        token_ok = await self.token_risk.check(signal.token_address)
        if not token_ok:
            return FAIL_TOKEN_RISK
        
        # 事件风控
        event_ok = await self.event_risk.check(signal)
        if not event_ok:
            return FAIL_EVENT_RISK
        
        return PASS
```

### 4. risk/take_profit.py — 止盈监控

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\risk\take_profit.py`

**直接复用：**

```python
# position/manager.py 中引用
from risk.take_profit import TakeProfitMonitor

# TakeProfitMonitor 作为一个独立的 asyncio task 运行
# 检查所有 open positions，ROI 达标则自动卖出
```

### 5. db/database.py — 数据库模式

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\db\database.py`

**复用思路：** 参考 `copy_trades` 表模式设计 DegenClaw 的 `trade_orders` 和 `positions` 表。特别是：
- 订单去重（`INSERT OR IGNORE`）
- 崩溃恢复（pending tx 检测）
- PnL 计算模式

### 6. config/loader.py — 配置框架

**原项目路径：** `D:\AAA-Project\015-OKX-Robot\src\config\loader.py`

**复用方式：**

```python
# 直接引用配置热加载机制
from config.loader import ConfigLoader, reload_yaml

# DegenClaw 的配置结构
class DegenClawConfig:
    strategy: StrategyConfig
    scoring: ScoringConfig
    liquidity: LiquidityConfig
    execution: ExecutionConfig
    
    @classmethod
    def load(cls) -> 'DegenClawConfig':
        loader = ConfigLoader()
        return cls(
            strategy=loader.load_yaml("config/strategy.yaml"),
            # ...
        )
```

## 环境依赖配置

### requirements.txt

```txt
# FastAPI + ASGI
fastapi>=0.116
uvicorn[standard]

# HTTP 客户端
httpx

# 数据库
aiosqlite

# 调度
APScheduler

# Web3 链上交互
web3>=6.0

# 配置解析
pyyaml
python-dotenv

# 引用 SignalHub (004) — 相对路径或 PYTHONPATH
# 运行时需设置 PYTHONPATH 包含 SignalHub src 路径
# export PYTHONPATH=$PYTHONPATH:/path/to/004-SignalHub/signalhub/app

# 引用 OKX-Robot (015) — 相对路径或 PYTHONPATH
# export PYTHONPATH=$PYTHONPATH:/path/to/015-OKX-Robot/src
```

### 环境变量 (.env)

```bash
# === 数据库 ===
DATABASE_PATH=data/degenclaw.db

# === SignalHub 引用路径 ===
SIGNALHUB_PATH=D:\\AAA-Project\\004-SignalHub\\signalhub\\app

# === OKX-Robot 引用路径 ===
OKXROBOT_PATH=D:\\AAA-Project\\015-OKX-Robot\\src

# === OKX DEX API ===
OKX_API_KEY=xxxx
OKX_SECRET_KEY=xxxx
OKX_PASSPHRASE=xxxx

# === Chainstack RPC ===
RPC_HTTP_URL=https://base-rpc.chainstack.com/xxxx
RPC_WSS_URL=wss://base-rpc.chainstack.com/xxxx

# === 交易钱包 ===
PRIVATE_KEY=xxxx
WALLET_ADDRESS=0x...

# === Web App ===
FRONTEND_URL=http://localhost:5173
```

## 与上游项目的同步策略

| 操作 | 频率 | 说明 |
|------|------|------|
| 检查 SignalHub 更新 | 每周 | git pull SignalHub main，验证兼容性 |
| 检查 OKX-Robot 更新 | 每周 | git pull OKX-Robot main，验证兼容性 |
| 回馈通用修改 | 需要时 | 对两个项目的改进做 PR 回馈 |

## 风险与规避

| 风险 | 影响 | 规避措施 |
|------|------|---------|
| SignalHub 改 API 格式 | 解析层出错 | 引用特定 commit，不跟踪最新 |
| OKX-Robot 换签名算法 | 交易失败 | 封装隔离层，修改仅影响 adapter |
| 两个项目 Python 版本冲突 | 依赖冲突 | 各自用 venv，DegenClaw 独立 requirements |
| 路径硬编码 | 部署困难 | 路径从环境变量读取 |

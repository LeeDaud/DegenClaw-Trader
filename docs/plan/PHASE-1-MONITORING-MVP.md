# Phase 1：只读监控 MVP

## 概述

构建一个只读数据系统，不做交易，只做监控和展示。这是整个项目的数据基础，所有后续阶段都依赖此阶段产出的数据链路。

## 核心目标

1. 搭建 Python FastAPI + React 项目骨架
2. 实现 SQLite 数据库与 schema（复用 SignalHub db 层）
3. 实现 collector-worker 定时采集（扩展 SignalHub sources）
4. 实现基础 API 服务提供数据
5. 实现基础前端看板展示数据
6. 实现日志与错误处理

## 代码复用说明

Phase 1 直接复用 **SignalHub (004)** 的以下模块：

| 复用模块 | 用途 |
|---------|------|
| `signalhub/app/sources/virtuals_source.py` | HTTP 轮询 + 重试 + 离线模式 |
| `signalhub/app/parsers/virtuals_parser.py` | API 响应解析 + 地址验证 |
| `signalhub/app/database/db.py` | SQLite 连接 + upsert + 迁移 |
| `signalhub/app/database/models.py` | 数据模型设计模式 |
| `signalhub/app/scheduler/polling.py` | APScheduler 定时任务框架 |

详见 [REUSE-STRATEGY.md](REUSE-STRATEGY.md)。

## 详细任务拆解

### 1.1 项目骨架搭建

#### 初始化项目结构

```
DegenClaw-Alpha-Engine/
├── frontend/
│   └── web/                      # React + Vite + Tailwind
│       ├── package.json
│       ├── vite.config.ts
│       ├── tsconfig.json
│       └── src/
│           ├── App.tsx
│           ├── main.tsx
│           └── pages/
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── main.py                   # FastAPI 入口（参考 SignalHub）
│   ├── config/
│   │   └── strategy.yaml
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             # FastAPI 路由（参考 SignalHub 模式）
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py           # SQLite 层（复用 SignalHub db.py）
│   │   └── models.py             # 数据模型（复用 SignalHub models.py）
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── degenclaw_collector.py  # DegenClaw 采集器
│   │   ├── market_collector.py     # 市场数据采集
│   │   └── signalhub_adapter.py    # SignalHub 适配
│   ├── parsers/
│   │   └── degenclaw_parser.py     # 解析器（扩展 SignalHub parser）
│   └── scheduler/
│       └── scheduler.py            # APScheduler（复用 SignalHub polling.py）
├── docs/
├── scripts/
└── .env.example
```

#### 依赖安装

**后端依赖（requirements.txt）：**

```
# FastAPI
fastapi>=0.116
uvicorn[standard]

# HTTP 客户端
httpx

# 数据库
aiosqlite

# 调度
APScheduler

# 配置
pyyaml
python-dotenv

# 日志
loguru

# PYTHONPATH 需要包含 SignalHub 和 OKX-Robot 源码路径
```

**前端依赖：**
- react + react-dom
- react-router-dom
- tailwindcss
- @shadcn/ui 组件
- recharts
- @tanstack/react-query

### 1.2 数据库实现

#### 复用 SignalHub 数据库层

参考 SignalHub 的 `signalhub/app/database/db.py` 实现 DegenClaw 数据库层。

**复用方式：**

```python
# db/database.py — 参考 SignalHub db.py 模式
import sqlite3
import aiosqlite
from dataclasses import dataclass

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        await self._init_tables()
    
    async def _init_tables(self):
        """初始化所有表（参考 SignalHub _ensure_entities_columns 模式）"""
        ...
```

**数据库文件路径：** `data/degenclaw.db`（由 .env 配置）

**核心表（按实现顺序）：**

| 表 | 优先级 | 说明 | 参考来源 |
|----|--------|------|---------|
| agents | P0 | Agent 基础信息 | SignalHub entities |
| agent_snapshots | P0 | Agent 排名与表现快照 | 新增 |
| tokens | P0 | Token 基础信息 | 新增 |
| token_market_snapshots | P0 | Token 市场数据 | 新增 |
| system_events | P0 | 系统事件日志 | SignalHub events |
| agent_scores | P1 | 评分结果（Phase 2 用）| 新增 |
| trade_signals | P1 | 交易信号（Phase 3 用）| 新增 |
| trade_orders | P2 | 订单（Phase 4 用）| OKX-Robot copy_trades |
| positions | P2 | 持仓（Phase 4 用）| OKX-Robot copy_trades |
| trade_reviews | P2 | 复盘（Phase 5 用）| 新增 |
| leaderboard_snapshots | P0 | 排行榜原始快照 | SignalHub project_snapshots |
| ai_pot_rounds | P0 | AI Pot 轮次信息 | 新增 |

#### 详细 Schema 定义

见 [DATABASE-SCHEMA.md](DATABASE-SCHEMA.md)

### 1.3 Collector Worker

#### 复用方式

直接扩展 SignalHub 的 `VirtualsSource`，利用其 HTTP 轮询、重试、离线模式能力：

```python
# collectors/signalhub_adapter.py
import sys
sys.path.append(env('SIGNALHUB_PATH'))

from sources.virtuals_source import VirtualsSource

class DegenClawSource(VirtualsSource):
    """扩展 SignalHub 的 HTTP 采集机制到 DegenClaw"""
    pass  # 具体实现见 REUSE-STRATEGY.md
```

#### 整体架构

```
APScheduler (每 5 分钟, 复用 SignalHub polling.py)
    │
    ├── DegenClawCollector ──── Agent 列表 + 排名 + 表现
    │   └── 复用 VirtualsSource 的 HTTP 轮询 + 重试
    │
    ├── DexScreenerCollector ── Token 价格 + 流动性 + 成交量
    │   └── 新增 httpx 采集
    │
    ├── TokenHolderCollector ── Token holder 数据
    │   └── 复用 SignalHub basescan_trace.py 链上逻辑
    │
    └── VirtualsCollector ───── AI Pot 状态 (低频率)
        └── 复用 VirtualsSource 的 endpoint 模式
```

#### 采集器设计

##### DegenClawCollector

```python
# collectors/degenclaw_collector.py
from collectors.signalhub_adapter import DegenClawSource

class DegenClawCollector(DegenClawSource):
    """DegenClaw 排行榜采集器"""
    
    async def fetch_leaderboard(self) -> list[AgentRaw]:
        """获取 Agent 排行榜"""
        raw = await self._fetch("degenclaw/leaderboard")
        return self._parse_leaderboard(raw)
    
    async def fetch_agent_detail(self, agent_id: str) -> AgentRaw:
        """获取单个 Agent 详情"""
        raw = await self._fetch(f"agents/{agent_id}")
        return self._parse_agent(raw)

@dataclass
class AgentRaw:
    id: str
    name: str
    rank: int
    pnl_24h: float
    pnl_7d: float
  pnl_7d: number;
  win_rate: number;
  max_drawdown: number;
  trade_count: number;
  is_top_10: boolean;
  is_selected?: boolean;
  token_address?: string;
}
```

##### DexScreenerCollector

```typescript
interface DexScreenerCollector {
  name: 'dexscreener';
  
  // 获取 token 市场数据（按地址查询）
  fetchTokenByAddress(address: string): Promise<TokenMarketRaw>;
  
  // 批量查询（限制 30 个地址）
  fetchTokensByAddresses(addresses: string[]): Promise<TokenMarketRaw[]>;
}

interface TokenMarketRaw {
  token_address: string;
  price_usd: number;
  liquidity_usd: number;
  volume_1h: number;
  volume_24h: number;
  price_change_1h: number;
  price_change_24h: number;
  buy_slippage?: number;
  sell_slippage?: number;
  pool_address: string;
  chain: string;
}
```

##### VirtualsCollector

```typescript
interface VirtualsCollector {
  name: 'virtuals';
  
  // 获取 AI Pot 当前状态
  fetchAIPotRound(): Promise<AIPotRoundRaw>;
  
  // 获取 AI Council 选择结果
  fetchCouncilResult(): Promise<CouncilResultRaw>;
}

interface AIPotRoundRaw {
  round_id: string;
  round_start: string;   // ISO datetime
  round_end: string;     // ISO datetime
  status: 'upcoming' | 'active' | 'ended';
  selected_agents: string[];
  pot_pnl?: number;
}
```

#### Mock 数据适配器

Phase 1 使用 MockAdapter 返回硬编码或模拟数据，确保代码结构可切换。

```typescript
interface CollectorAdapter<T> {
  readonly name: string;
  readonly source: 'mock' | 'real';
  
  fetch(): Promise<T>;
  healthCheck(): Promise<boolean>;
}

// 每个 collector 同时实现 mock 和 real 两个 adapter
// 通过环境变量 COLLECTOR_SOURCE=mock|real 切换
```

#### 采集流程

```
每 5 分钟:
1. ┌─ DegenClawCollector.fetchLeaderboard()
2. ├─ 保存 agent_snapshots（批量）
3. ├─ 提取 token_address 列表
4. ├─ DexScreenerCollector.fetchTokensByAddresses(tokens)
5. ├─ 保存 token_market_snapshots（批量）
6. ├─ 检查 AI Pot 状态（每 30 分钟）
7. └─ 记录 system_events（采集完成/异常）
```

#### 错误处理

- 单次采集失败不影响下次采集
- 采集异常记录到 system_events 表
- 连续 3 次失败触发告警（日志 + 控制台输出）
- 每个 collector 独立 try/catch

### 1.4 API 服务

#### 路由设计

```
GET /api/v1/agents
  └─ 返回当前 Agent 列表（含最新评分，Phase 2 后）

GET /api/v1/agents/:id
  └─ 返回 Agent 详情 + 排名历史 + token 数据

GET /api/v1/agents/:id/snapshots
  └─ 返回 Agent 快照历史（分页）

GET /api/v1/tokens/:address
  └─ 返回 Token 详情 + 市场数据

GET /api/v1/tokens/:address/snapshots
  └─ 返回 Token 市场快照历史

GET /api/v1/dashboard
  └─ 返回系统总览数据

GET /api/v1/events
  └─ 返回系统事件日志（分页）

GET /api/v1/health
  └─ 健康检查
```

#### 响应格式

```typescript
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
  timestamp: string;
}

interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
}
```

### 1.5 前端看板

#### 页面清单

##### Dashboard 首页 (`/`)

```
┌──────────────────────────────────────────────┐
│  System Status │ Agents: 50 │ Signals: 3     │
│  Event Window: pre_selection                 │
│  Risk Level: medium                          │
├──────────────────────────────────────────────┤
│  Top Movers (24h)        │ Risk Alerts       │
│  ┌───┐   ┌───┐   ┌───┐  │ ┌──────────────┐ │
│  │A1 │   │A2 │   │A3 │  │ │ Low liquidity │ │
│  └───┘   └───┘   └───┘  │ │ Price spike   │ │
│                          │ └──────────────┘ │
├──────────────────────────────────────────────┤
│  Recent Signals                               │
├──────────────────────────────────────────────┤
│  System Events                                │
└──────────────────────────────────────────────┘
```

##### Agent Leaderboard (`/agents`)

```
┌─────────────────────────────────────────────────────────────┐
│ Rank │ Agent │ Token │ Score │ RankΔ │ 24h PnL │ 7d PnL │ AI Pot │ Action │
├──────┼───────┼───────┼───────┼───────┼─────────┼────────┼────────┼────────┤
│ #1   │ AXP   │ $AXP  │ 85    │ ↑3    │ +12.5%  │ +45%   │ ✓      │ watch  │
│ #2   │ BZX   │ $BZX  │ 72    │ ↓1    │ -3.2%   │ +22%   │ ✗      │ watch  │
│ ...  │       │       │       │       │         │        │        │        │
└─────────────────────────────────────────────────────────────┘
```

##### Agent Detail (`/agents/:id`)

```
┌────────────────────────────────────────────┐
│ Agent Name          Rank: #7  ↑2           │
│ Token: $AXP  0x1234...5678                 │
├────────────────────────────────────────────┤
│ Rank Trend (7d chart)                      │
│  ┌──────────────────────────────────────┐  │
│  │       Line chart of rank over time   │  │
│  └──────────────────────────────────────┘  │
├────────────────────────────────────────────┤
│ Score Breakdown  │ Token Market            │
│  Council: 30/35  │ Price: $0.42            │
│  Performance:16  │ Liq: $120K              │
│  Rank Trend: 12  │ Vol 24h: $45K           │
│  Token Mkt: 11   │ Slippage: 1.2%          │
│  Visibility: 9   │ Holders: 342            │
│  Risk Penalty: -6│                         │
├────────────────────────────────────────────┤
│ Performance: 7d PnL │ Win Rate │ Drawdown  │
└────────────────────────────────────────────┘
```

##### Token Market (`/tokens`)

```
┌──────────────────────────────────────────────────────────┐
│ Token     Price    Liq       Vol 24h       Change 1h/24h │
│ $AXP      $0.42    $120K     $45K          +2.1% / +35%  │
│ $BZX      $1.23    $85K      $22K          -0.5% / +12%  │
└──────────────────────────────────────────────────────────┘
```

##### System Logs (`/logs`)

```
┌──────────────────────────────────────────────┐
│ Time         Module     Level   Event        │
│ 12:00:05     collector  info    采集完成       │
│ 11:55:03     collector  warn    DexScreener   │
│                              请求超时，已重试  │
└──────────────────────────────────────────────┘
```

#### UI 实现要点

- 使用 shadcn/ui 组件库
- Table 组件实现数据列表（支持排序）
- Recharts 实现时序图表
- 使用 @tanstack/react-query 管理 API 请求
- 响应式布局（移动端可用）
- 深色模式支持

### 1.6 日志系统

#### 日志级别

```
fatal: 系统不可用，需要立即干预
error: 功能异常，不影响整体运行
warn: 潜在问题，需要注意
info: 正常运行信息
debug: 调试信息（仅开发环境）
```

#### 日志实现

```typescript
interface LogEntry {
  time: string;          // ISO 8601
  module: string;        // collector | api | scoring | signal | ...
  level: 'fatal' | 'error' | 'warn' | 'info' | 'debug';
  event: string;         // 简短事件名
  detail?: string;       // 详情
  trace_id?: string;     // 追踪 ID
}

// 输出到两个目标：
// 1. 控制台（pino 格式）
// 2. system_events 表（持久化）
```

#### 日志分类

| 日志类别 | 模块前缀 | 说明 |
|---------|---------|------|
| collector_log | cw | 采集相关 |
| scoring_log | sw | 评分相关 |
| signal_log | sigw | 信号相关 |
| risk_log | rcx | 风控相关 |
| execution_log | exec | 执行相关 |
| position_log | posw | 持仓相关 |
| review_log | revw | 复盘相关 |

## 验收标准

- [ ] 系统可以连续运行 24 小时
- [ ] 数据每 5 分钟更新一次
- [ ] 前端可以查看 top 50 Agent
- [ ] 前端可以查看每个 Agent 对应 token 的价格与流动性
- [ ] 系统崩溃后可自动重启（PM2）
- [ ] 采集失败时系统日志记录完整
- [ ] 所有 API 返回一致格式
- [ ] 数据库文件正确创建，表结构完整
- [ ] Mock 数据可切换为真实数据而无需改代码

## 技术债务（允许的）

- Mock 数据硬编码（Phase 0 完成后替换）
- 无前端状态持久化（Phase 2 加入）
- 无用户认证（始终单用户）
- 无自动化测试（Phase 2 补充核心逻辑测试）

## 未解决问题（Phase 1 结束后记录）

- [ ] 哪些数据源在实际测试中不可用？
- [ ] 5 分钟采集间隔在真实数据源下是否可行？
- [ ] DexScreener API 的批量查询限制是否影响 50 个 Agent 的采集？

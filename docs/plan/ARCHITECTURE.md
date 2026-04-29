# 系统架构总览

## 项目定位

DegenClaw Agent Token 事件驱动型交易系统。不是炒币机器人，也不是看板工具，而是由**数据采集 → 信号生成 → 评分模型 → 交易决策 → 风控执行 → 交易复盘**组成的闭环系统。

## 六层架构

```
┌─────────────────────────────────────────────────┐
│                  复盘分析层                        │
│  Review Engine · 策略统计 · 因子有效性分析        │
├─────────────────────────────────────────────────┤
│                  交易执行层                        │
│  Trade Executor · Position Manager · Risk Control │
├─────────────────────────────────────────────────┤
│                  评分决策层                        │
│  Agent Scoring · Trading Decision · Event Window  │
├─────────────────────────────────────────────────┤
│                  信号生成层                        │
│  排名趋势 · 表现改善 · 量价信号 · 事件信号        │
├─────────────────────────────────────────────────┤
│                  数据存储层                        │
│  SQLite → PostgreSQL · 快照 · 信号 · 订单 · 复盘   │
├─────────────────────────────────────────────────┤
│                  数据采集层                        │
│  DegenClaw · Virtuals · DEX · 链上 · 价格API     │
└─────────────────────────────────────────────────┘
```

## 核心交易逻辑

系统交易的核心不是单个 token 的价格走势，而是以下组合变量：

1. **AI Council 选择概率** — Agent 是否可能被选中进入 AI Pot
2. **AI Pot copy-trading 预期** — Agent 是否已进入 copy-trading
3. **Agent Token buyback 预期** — 收益回购对价格的推动
4. **市场注意力扩散速度** — 排名变化、社区讨论
5. **Token 流动性与价格动量** — 流动性深度、滑点、量价结构

## 技术栈

| 层 | 技术 | 来源 |
|---|---|---|
| 后端运行时 | Python 3.11+ | — |
| Web 框架 | FastAPI | 复用 SignalHub 框架 |
| 数据库 | SQLite（起步）→ PostgreSQL（扩展） | — |
| ORM | 原生 SQLite（aiosqlite）/ 自定义 | 复用 SignalHub db 层 |
| 定时任务 | APScheduler | 复用 SignalHub scheduler |
| 前端 | React + Vite + Tailwind CSS + shadcn/ui + Recharts | — |
| 数据采集 | Virtuals API + DexScreener + Base RPC | 复用 SignalHub sources/parsers |
| 交易执行 | OKX DEX Aggregator API | 复用 OKX-Robot executor/okx_client |
| 链上数据 | Chainstack RPC/WSS | 复用 SignalHub explorer/monitor |
| 部署 | Ubuntu VPS · PM2 · Nginx | — |

> **技术栈决策理由：** SignalHub (004) 和 OKX-Robot (015) 均为 Python 项目，改用 Python/FastAPI 可实现最大代码复用，减少重复开发。前端保持 React/Vite 不变。

## 代码复用策略

本项目直接复用两个现有项目的代码模块，避免重复造轮子：

### 来自 SignalHub (004)

| 模块 | 路径 | 复用方式 |
|---|---|---|
| Virtuals API 轮询 | `signalhub/app/sources/virtuals_source.py` | 扩展采集 DegenClaw leaderboard |
| API 响应解析 | `signalhub/app/parsers/virtuals_parser.py` | 新增 DegenClaw 字段映射 |
| 评分引擎框架 | `signalhub/app/scoring/score_engine.py` | 替换评分因子，框架复用 |
| 生命周期引擎 | `signalhub/app/lifecycle/lifecycle_engine.py` | 直接映射到事件窗口 |
| 快照变化检测 | `signalhub/app/diff/diff_engine.py` | 直接复用 |
| SQLite 数据库层 | `signalhub/app/database/db.py` | 扩展表结构 |
| 链上交易追踪 | `signalhub/app/explorer/basescan_trace.py` | 用于 token holder/pool 分析 |
| WebSocket 监控 | `signalhub/app/subscriptions/chainstack_launch_monitor.py` | 实时监控 token 交易 |

### 来自 OKX-Robot (015)

| 模块 | 路径 | 复用方式 |
|---|---|---|
| OKX DEX API 封装 | `okx-robot/src/executor/okx_client.py` | 直接复用 |
| 交易执行 | `okx-robot/src/executor/trader.py` | 复用 approve/swap/sell 流程 |
| 日亏损风控 | `okx-robot/src/risk/guard.py` | 扩展为全局风控 |
| 止盈监控 | `okx-robot/src/risk/take_profit.py` | 直接复用 |
| 订单/持仓数据库 | `okx-robot/src/db/database.py` | 复用表结构设计 |
| YAML 配置热加载 | `okx-robot/src/config/loader.py` | 复用配置框架 |
| Swap 事件解码 | `okx-robot/src/monitor/decoder.py` | 需要时复用 |

## 模块全景

| 模块 | 类型 | 运行频率 | 职责 | 复用来源 |
|---|---|---|---|---|
| collector-worker | worker | 每 5 分钟 | 采集 Agent 和 token 数据 | SignalHub sources 扩展 |
| scoring-worker | worker | 每 1 小时 | 计算 Agent 评分 | SignalHub scoring 框架 |
| signal-worker | worker | 每 15 分钟 | 生成交易信号 | 新增 |
| executor-service | service | 事件驱动 | 执行交易指令 | OKX-Robot executor |
| position-worker | worker | 每 1 分钟 | 持仓监控与退出 | OKX-Robot 扩展 |
| review-worker | worker | 事件驱动 | 生成复盘 | 新增 |
| API Server | service | 持续 | 提供前端数据 | FastAPI（SignalHub 模式）|
| Web App | frontend | 持续 | 用户界面 | React |

## 推荐目录结构

```
DegenClaw-Alpha-Engine/
├── frontend/
│   └── web/                    # React 前端（Vite + Tailwind）
├── backend/
│   ├── api/                    # FastAPI 路由
│   ├── db/                     # 数据库层（复用 SignalHub db.py 模式）
│   ├── collectors/             # 采集器（复用 SignalHub sources）
│   │   ├── degenclaw/          # DegenClaw 专用采集
│   │   └── market/             # 市场数据采集（扩展 SignalHub）
│   ├── scoring/                # 评分引擎（复用 SignalHub scoring 框架）
│   ├── decision/               # 交易决策 + 事件窗口
│   ├── executor/               # 交易执行（直接引用 OKX-Robot 模块）
│   │   └── vendor/             # OKX-Robot 源码链接
│   ├── risk/                   # 风控（复用 OKX-Robot risk 模块）
│   └── scheduler/              # 调度器（复用 SignalHub APScheduler）
├── config/
│   ├── strategy.yaml           # 策略配置
│   └── scoring.yaml            # 评分配置
├── docs/
├── scripts/
└── .env.example
```

## 项目间依赖关系

```
SignalHub (004) ──sources/parsers/scoring──→ DegenClaw Alpha Engine
                        ↑                           │
                  复用 Python 模块             复用 Python 模块
                        │                           ↓
OKX-Robot (015) ─────executor/risk──────────→ DegenClaw Alpha Engine
```

## 阶段路线图

```
Phase 0 ─→ Phase 1 ─→ Phase 2 ─→ Phase 3 ─→ Phase 4 ─→ Phase 5 ─→ Phase 6
调研确认    只读监控    评分模型    交易信号    半自动交易   自动交易    策略优化

                                            ↑ SignalHub 复用开始
                                            ↑ OKX-Robot 复用开始
```

各阶段详情见对应 PHASE-N-*.md 文档。

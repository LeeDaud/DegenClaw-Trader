# 阶段规划总览

## 开发顺序

```
Phase 0 ─→ Phase 1 ─→ Phase 2 ─→ Phase 3 ─→ Phase 4 ─→ Phase 5 ─→ Phase 6
调研确认    只读监控    评分模型    交易信号    半自动交易   自动交易    策略优化

                                        │
                                        ▼
                                 所有阶段无真实交易
                                 直到 Phase 4 才接入真实机器人
                                 直到 Phase 5 才允许自动下单
```

## 依赖关系

| 阶段 | 依赖 | 可并行 |
|------|------|--------|
| Phase 0 | 无 | — |
| Phase 1 | Phase 0, SignalHub 项目存在 | — |
| Phase 2 | Phase 1, SignalHub scoring 框架 | — |
| Phase 3 | Phase 2 | — |
| Phase 4 | Phase 3, OKX-Robot 项目存在 | — |
| Phase 5 | Phase 4 | — |
| Phase 6 | Phase 3-5 | 可与 4/5 并行 |

## 各阶段核心产出

| 阶段 | 核心产出 | 验收标准摘要 | 复用来源 |
|------|---------|-------------|---------|
| P0 | 数据源清单 + schema 草案 | 能稳定获取 top50 Agent、关联 token 地址 | — |
| P1 | 采集服务 + SQLite + 看板 | 连续运行 24h，每 5 分钟更新，前端可见 | SignalHub sources/db |
| P2 | 评分引擎 + 评分结果 + 趋势图 | 每小时自动评分，因子可配置，评分可解释 | SignalHub scoring |
| P3 | 决策引擎 + paper trading | 连续 30+ 信号，有入场/退出/风控参数，可完整复盘 | — |
| P4 | 确认页面 + 机器人适配器 | 用户可批准/拒绝，机器人正确接收指令 | OKX-Robot executor |
| P5 | 自动风控 + 自动退出 | 完整买卖闭环，风控触发自动停机 | OKX-Robot risk |
| P6 | 策略分析 + 因子有效性 | 输出策略周报，识别高胜率信号类型 | — |

## 关键决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| **后端语言** | **Python 3.11+** | SignalHub 和 OKX-Robot 均为 Python，直接复用代码模块 |
| **Web 框架** | **FastAPI** | 复用 SignalHub 成熟的 FastAPI 架构 |
| 评分模型 | 规则评分 (非 ML) | 第一阶段可解释性优先，数据量不足以支撑 ML |
| 数据库起步 | SQLite | 快速启动，单机部署简单 |
| LLM 角色 | 辅助复盘/解释，不参与决策 | 保证交易决策可审计、可重复 |
| 交易模式 | 纯 paper → 半自动 → 自动 | 逐步验证，不允许跳级 |
| 实时性 | 5 分钟采集 + 15 分钟信号 + 1 分钟持仓 | 事件驱动型策略不需要高频 |
| **交易执行** | **复用 OKX-Robot executor** | 已有完整的 OKX DEX API 对接和交易流程 |
| **数据采集** | **复用 SignalHub sources** | 已有 Virtuals API 轮询和解析框架 |
| **链上数据** | **复用 SignalHub explorer** | 已有 Chainstack RPC/WSS 集成 |

## 代码复用结构

```
本项目代码（新增）
┌─────────────────────────────────────┐
│  degenclaw/collectors/DegenClaw     │  DegenClaw 专用采集
│  degenclaw/scoring/DegenClawScorer  │  DegenClaw 专用评分
│  degenclaw/decision/                 │  交易决策引擎
│  degenclaw/signal/                   │  信号生成
│  degenclaw/risk/DegenClawRisk        │  扩展风控
│  frontend/                           │  React 前端
└─────────────────────────────────────┘

代码直接引用（不复制，通过 PYTHONPATH 或 git submodule）
┌──────────────────────┐  ┌─────────────────────────┐
│  SignalHub (004)     │  │  OKX-Robot (015)        │
│  ├─ sources/         │  │  ├─ executor/okx_client │
│  ├─ parsers/         │  │  ├─ executor/trader     │
│  ├─ scoring/         │  │  ├─ risk/guard          │
│  ├─ database/        │  │  ├─ risk/take_profit    │
│  ├─ lifecycle/       │  │  ├─ db/database         │
│  ├─ diff/            │  │  └─ config/loader       │
│  ├─ explorer/        │  │                         │
│  └─ subscriptions/   │  │                         │
└──────────────────────┘  └─────────────────────────┘
```

## 风控优先级

系统各模块的执行优先级：

```
Risk Control Engine ── 最高优先级，拦截一切
       │
       ▼
Position Manager ── 强制退出权，不依赖决策引擎
       │
       ▼
Trade Executor ── 执行前二次检查，可拒单
       │
       ▼
Trading Decision Engine ── 生成建议
       │
       ▼
Agent Scoring Engine ── 提供评分基础
```

风控不可被覆盖。即使评分和决策都建议买入，风控拒绝则交易不执行。

## 各阶段详细文档

- [代码复用详细方案](REUSE-STRATEGY.md)
- [Phase 0: 信息调研与数据确认](PHASE-0-RESEARCH.md)
- [Phase 1: 只读监控 MVP](PHASE-1-MONITORING-MVP.md)
- [Phase 2: 评分模型 MVP](PHASE-2-SCORING-MVP.md)
- [Phase 3: 交易信号 MVP](PHASE-3-SIGNAL-MVP.md)
- [Phase 4: 半自动交易](PHASE-4-SEMI-AUTO-TRADING.md)
- [Phase 5: 小资金自动交易](PHASE-5-AUTO-TRADING.md)
- [Phase 6: 策略优化与扩展](PHASE-6-OPTIMIZATION.md)

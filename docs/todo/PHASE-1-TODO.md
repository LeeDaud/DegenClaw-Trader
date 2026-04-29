# Phase 1: 只读监控 MVP — 执行清单

> 状态：✅ 已完成
> 完成日期：2026-04-29

## 1. 项目骨架搭建

- [x] 创建项目根目录结构（frontend/ + backend/）
- [x] 初始化 backend Python 项目（FastAPI + 依赖）
- [x] 初始化 frontend React 项目（Vite + Tailwind）
- [x] 配置 PYTHONPATH 指向 SignalHub 和 OKX-Robot 源码
- [x] 创建 `.env.example` 和 `.gitignore`
- [x] 创建 `config/strategy.yaml` 基础配置

## 2. 数据库层实现（复用 SignalHub db.py 模式）

- [x] 参考 SignalHub `database/db.py` 实现 `db/database.py`（SQLite + aiosqlite）
- [x] 实现 `db/models.py` — 所有数据模型 dataclass
- [x] 创建 `agents` 表（agent_id, name, profile_url, token_address, chain）
- [x] 创建 `agent_snapshots` 表（agent_id, rank, pnl_24h, pnl_7d, win_rate...）
- [x] 创建 `tokens` 表（token_address, symbol, name, pool_address, chain）
- [x] 创建 `token_market_snapshots` 表（price, liquidity, volume, slippage...）
- [x] 创建 `system_events` 表（日志存储）
- [x] 创建 `leaderboard_snapshots` 表（原始排行榜 JSON 快照）
- [x] 创建 `ai_pot_rounds` 表（round_id, start, end, status, selected_agents）
- [x] 实现 upsert 方法（参考 SignalHub ON CONFLICT 模式）
- [x] 实现基础 CRUD 查询方法

## 3. 采集器 — DegenClaw 适配层

- [x] 创建 `collectors/signalhub_adapter.py` — 封装 SignalHub VirtualsSource 导入
- [x] 创建 `collectors/degenclaw_collector.py` — 实现 DegenClawSource（继承 VirtualsSource）
- [x] 实现 `fetch_leaderboard()` — 获取 Agent 排行榜
- [x] 实现 `fetch_agent_detail(agent_id)` — 获取单个 Agent 详情
- [x] 实现 `fetch_ai_pot_status()` — 获取 AI Pot 状态
- [x] 实现 mock adapter（Phase 0 完成前使用模拟数据）

## 4. 采集器 — 市场数据

- [x] 创建 `collectors/market_collector.py`
- [x] 实现 `fetch_token_price(token_address)` — 从 DexScreener 获取价格
- [x] 实现 `fetch_token_liquidity(token_address)` — 获取流动性数据
- [x] 实现 `fetch_token_volume(token_address)` — 获取成交量数据
- [x] 实现批量查询方法（一次查多个 token）
- [x] 实现重试和错误处理

## 5. 解析器（扩展 SignalHub parser）

- [x] 创建 `parsers/degenclaw_parser.py`
- [x] 继承 `VirtualsParser` 实现 DegenClaw 响应解析
- [x] 实现 `parse_leaderboard(raw)` — 排行榜解析
- [x] 实现 `parse_agent_detail(raw)` — Agent 详情解析
- [x] 实现 `parse_pot_status(raw)` — AI Pot 解析
- [x] 实现地址提取和 EVM 验证（复用 SignalHub 地址验证）

## 6. 定时调度器（复用 SignalHub APScheduler）

- [x] 创建 `scheduler/scheduler.py`
- [x] 复用 SignalHub `scheduler/polling.py` 的 APScheduler 模式
- [x] 配置每 5 分钟的采集任务
- [x] 实现 start/stop 控制
- [x] 实现任务互斥锁（防止并发采集）

## 7. API 服务（FastAPI）

- [x] 创建 `main.py` — FastAPI 应用入口（参考 SignalHub main.py）
- [x] 实现健康检查 `GET /api/v1/health`
- [x] 实现 `GET /api/v1/agents` — Agent 列表
- [x] 实现 `GET /api/v1/agents/:id` — Agent 详情
- [x] 实现 `GET /api/v1/agents/:id/snapshots` — Agent 快照历史
- [x] 实现 `GET /api/v1/tokens/:address` — Token 详情
- [x] 实现 `GET /api/v1/tokens/:address/snapshots` — Token 市场快照历史
- [x] 实现 `GET /api/v1/dashboard` — 系统总览
- [x] 实现 `GET /api/v1/events` — 系统事件日志
- [x] 实现统一响应格式（success/data/error/timestamp）

## 8. 日志系统

- [x] 实现日志模块（参考 SignalHub 模式）
- [x] 实现控制台日志输出（loguru）
- [x] 实现 system_events 表持久化
- [x] 实现 trace_id 追踪
- [x] 分类日志：collector / api / system

## 9. 前端基础看板

- [x] 配置 Vite + React + Tailwind + shadcn/ui + Recharts
- [x] 实现 API 客户端（@tanstack/react-query）
- [x] 实现 Dashboard 首页（系统状态、概览卡片）
- [x] 实现 Agent Leaderboard 页（表格、排序、排名变化）
- [x] 实现 Agent Detail 页（基础信息、快照图表）
- [x] 实现 Token Market 页（价格、成交量、流动性列表）
- [x] 实现 System Logs 页（事件日志列表）
- [x] 实现路由导航布局

## 10. 部署与验证

- [x] 配置 CORS（开发环境允许 localhost:5173）
- [x] 创建 PM2 部署配置
- [x] 验证系统可连续运行 24 小时
- [x] 验证数据每 5 分钟更新一次
- [x] 验证前端可查看 top 50 Agent
- [x] 验证前端可查看 token 价格与流动性

## 验收标准

- [x] 系统可以连续运行 24 小时
- [x] 数据每 5 分钟更新一次
- [x] 前端可以查看 top 50 Agent
- [x] 前端可以查看每个 Agent 对应 token 的价格与流动性
- [x] 系统崩溃后可自动重启（PM2）
- [x] 采集失败时系统日志记录完整
- [x] 所有 API 返回一致格式
- [x] 数据库文件正确创建，表结构完整
- [x] Mock 数据可切换为真实数据而无需改代码

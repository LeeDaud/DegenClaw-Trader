# DegenClaw Agent Token 交易系统

## 项目简介
监控 Virtuals 平台 DegenClaw 参赛 Agent，采集链上数据与交易表现，生成评分与交易信号，实现 Agent Token 的事件驱动型自动交易。

## 技术栈
- **后端**: Python 3.13, FastAPI, uvicorn
- **数据库**: SQLite (aiosqlite)
- **前端**: React 19, TypeScript, Vite 8, TailwindCSS 4, TanStack Query, Recharts
- **定时任务**: APScheduler
- **部署**: PM2, nginx

## 目录结构
| 路径 | 用途 |
|------|------|
| `backend/` | FastAPI 后端：API 路由、采集器、评分引擎、决策引擎、信号引擎、调度器、通知 |
| `backend/collectors/` | 数据采集：DegenClaw 排行榜、DexScreener 价格、赛季管理 |
| `backend/parsers/` | DegenClaw 页面解析 |
| `backend/scoring/` | Agent 评分引擎 |
| `backend/decision/` | 交易决策引擎、事件窗口、模拟交易 |
| `backend/signals/` | 交易信号生成 |
| `backend/scheduler/` | 轮询调度控制器 |
| `backend/notifiers/` | 飞书通知 |
| `frontend/web/` | React 前端：Dashboard、Agent 列表/详情、信号、持仓、Token 市场、日志 |
| `data/` | SQLite 数据库文件 |
| `deploy/` | 部署配置：nginx、PM2、环境变量 |
| `scripts/` | 辅助脚本：数据库初始化、后端启动 |
| `docs/` | 设计文档、API 文档、数据源说明、分阶段 TODO |
| `Prd.md` | 项目需求文档 |

## 验证命令
```bash
# 后端启动
cd backend && uvicorn main:app --reload --port 8000

# 前端启动
cd frontend/web && npm run dev

# 前端构建
cd frontend/web && npm run build
```

## 项目特有约定
- 配置走环境变量，通过 `backend/config/settings.py` 的 `Settings` dataclass 集中管理
- 数据库使用 SQLite，schema 由 `backend/db/models.py` 中的 dataclass 定义
- 当前进度：Phase 3（交易信号 MVP）完成，已实现采集/评分/决策/信号/前端全链路
- 核心数据流：采集器 → 解析器 → 评分引擎 → 决策引擎 → 信号引擎 → 前端展示
- 项目阶段文档在 `docs/plan/`，TODO 列表在 `docs/todo/`

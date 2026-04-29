# DegenClaw Trader

监控 Virtuals 平台 DegenClaw 参赛 Agent，采集链上数据与交易表现，生成评分与交易信号，实现 Agent Token 的事件驱动型自动交易。

## 架构

```
采集层  →  解析层  →  评分引擎  →  决策引擎  →  信号引擎  →  前端展示
                        ↘                                    ↙
                      模拟交易 ← 事件窗口 ← 飞书通知
```

六层架构：

| 层 | 职责 |
|---|---|
| 数据采集 | DegenClaw 排行榜 · DexScreener 价格 · 赛季管理 |
| 数据存储 | SQLite · Agent 快照 · Token 市场快照 · 评分 · 信号 · 持仓 |
| 评分引擎 | 五维评分（入选概率 + 交易表现 + 排名趋势 + Token 市场 + 可见度） |
| 决策引擎 | 事件窗口 · 多因子决策 · 买入/卖出/观望信号 |
| 信号引擎 | 阈值规则 · 排名趋势 · 表现改善 · 量价信号 |
| 前端 | Dashboard · Agent 列表/详情 · 信号 · 持仓 · Token 市场 |

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13, FastAPI, uvicorn |
| 数据库 | SQLite (aiosqlite) |
| 定时任务 | APScheduler |
| 前端 | React 19, TypeScript, Vite 8, TailwindCSS 4, TanStack Query, Recharts |
| 部署 | systemd, Nginx, Ubuntu VPS |
| 通知 | 飞书 Webhook |

## 目录结构

```
backend/
├── api/            # FastAPI 路由
├── collectors/     # DegenClaw / DexScreener / AI Pot 采集器
├── config/         # 集中配置
├── db/             # 数据库模型与操作
├── decision/       # 交易决策引擎、事件窗口、模拟交易
├── notifiers/      # 飞书通知
├── parsers/        # DegenClaw 页面解析
├── scheduler/      # 轮询调度控制器
├── scoring/        # Agent 评分引擎
├── signals/        # 交易信号生成
├── logger/         # 日志
└── main.py         # FastAPI 入口

frontend/web/       # React 前端
data/               # SQLite 数据库
deploy/             # 部署配置（nginx, env, 部署脚本）
docs/               # 设计文档、TODO
```

## 数据流

```
DegenClaw API → 采集器 → 赛季过滤 → 解析器 → 数据库
                    ↓
              DexScreener → Token 市场数据 → 数据库
                    ↓
              评分引擎 → 评分 → 数据库
                    ↓
              决策引擎 → 交易信号 → 数据库
                    ↓
              模拟交易 → 持仓 → 数据库
                    ↓
              API → 前端展示
```

## 本地开发

```bash
# 后端
cd backend
uvicorn main:app --reload --port 8000

# 前端
cd frontend/web
npm run dev
```

配置通过环境变量管理（参见 `backend/config/settings.py`），默认使用 mock 数据源。切换为实时数据需设置 `COLLECTOR_SOURCE=degenclaw` 和 `DEGENCLAW_ENDPOINT`。

## 部署

生产环境部署在 Ubuntu VPS，systemd 管理：

- **服务**: `degenclaw.service`
- **路径**: `/opt/degenclaw`
- **端口**: 8002（本地）
- **域名**: `degen.licheng.website`
- **HTTPS**: Let's Encrypt (Nginx)

```bash
# 更新代码
cd /opt/degenclaw && git pull origin master && systemctl restart degenclaw

# 日志
journalctl -u degenclaw -f
```

## 项目状态

- Phase 3（交易信号 MVP）已完成
- 核心链路：采集 → 评分 → 决策 → 信号 → 模拟交易 → 前端展示 已跑通
- 赛季自动检测 + 当季 Agent 过滤已集成
- 飞书预警通知已启用

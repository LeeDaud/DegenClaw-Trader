# AIPOT 集成规划：数据展示 + PnL监控 + 评委会评分

## 背景

当前 `AIPotCollector` 仅有 mock 数据。实际调研发现 `degen.virtuals.io` 有两个公开 API：
- `/api/pot-agents` — 10 个子池的实时数据（资金、PnL、持仓）
- `/api/council?seasonId=N` — AI 评委会评选数据（finalTop10、consensusAgents、模型打分理由）

无需 JWT，直接可用。

## 整体架构变更

```
degen.virtuals.io API
    ├── /api/pot-agents  ──→ AIPotCollector ──→ DB (pot_sub_agents + snapshots)
    └── /api/council      ──→ AIPotCollector ──→ DB (council_evaluations + scores)
                                                        │
                    ┌───────────────────────────────────┘
                    ▼
            FastAPI 新端点
    ├── GET /ai-pot/rounds        ──→ React /ai-pot 页面
    ├── GET /ai-pot/council       ──→ React /ai-pot 页面
    ├── GET /ai-pot/raw           ──→ React /ai-pot 页面 (调试用)
    ├── GET /agents (增强)        ──→ AgentList 多两列
    └── GET /dashboard (增强)     ──→ 首页 Pot 卡片
                    │
                    ▼
            监控引擎 (每 5 分钟)
    ├── 对比 PnL 快照 → 超阈值 → 飞书通知 + 涨跌预判
```

## 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| pot-agents 存储 | 结构化表 + 原始 JSON | 既要 R1 原样展示又要 R2 趋势分析 |
| council 存储 | 结构化表 + 原始 JSON | R3 需要按 agent_name 排序到 AgentList |
| 监控调度 | 复用现有 5min 轮询 | 不引入新调度器，复用错误处理/锁/飞书 |
| 涨跌预判 | 简单趋势：最近3次快照比较 | R1 要求原样展示，浅层预判足矣 |
| 前端 AIPot 页面 | 单页 4 区段 (Tab 切换) | 数据都来自 /ai-pot/* 端点，页面不复杂 |

## 实施步骤 (依赖顺序)

### Phase 1: 数据库层

**修改文件：** `backend/db/models.py`, `backend/db/database.py`

1. 新增 5 个 dataclass：
   - `PotSubAgent` — 子池数据（round_id, name, agent_id, agent_name, token_symbol, starting_capital, current_value, realized_pnl, unrealized_pnl, final_pnl, positions_json, status）
   - `CouncilEvaluation` — 评委会评选记录（season_id, pot_size, total_agents_analyzed, consensus_agents, model_verdicts, raw_data）
   - `CouncilAgentScore` — 评委会给每个 agent 的打分 (season_id, agent_name, rank, votes, per_model_rationale)
   - `PotPnlSnapshot` — PnL 快照历史（sub_pot_id, round_id, current_value, realized_pnl, final_pnl, snapshot_at）
   - `CouncilLeaderboardScore` — agent_id → council 分数映射（用于 AgentList 展示）

2. 新增 5 个表（CREATE TABLE IF NOT EXISTS）+ 索引 + CRUD

3. 增强 `AIPotRound`：增加 season_id, total_capital, total_current_value, total_realized_pnl, return_pct, raw_data

### Phase 2: 采集器

**修改文件：** `backend/collectors/degenclaw_collector.py`

1. 重构 `AIPotCollector`：`fetch_pot_status()` → 返回聚合 dict
2. 新增 `_fetch_pot_agents()` → GET /api/pot-agents
3. 新增 `_fetch_council(season_id)` → GET /api/council?seasonId=N
4. 新增 `fetch_raw_pot_agents()` / `fetch_raw_council()` → 原样返回
5. 更新 mock 数据

### Phase 3: 调度器 + 监控引擎

**修改文件：** `backend/scheduler/scheduler.py`
**新增文件：** `backend/monitoring/pot_monitor.py`

1. `run_collection()` 中：遍历 sub_pots → upsert DB + 记录 PnL 快照 + 存储 council data
2. `PotPnlMonitor`：对比快照 → 超阈值 → 飞书通知 + 涨跌预判

### Phase 4: 后端 API

**修改文件：** `backend/api/routes.py`

| Method | Path | 用途 |
|--------|------|------|
| GET | `/ai-pot/rounds` | 返回 pot rounds 列表（含 sub_pots） |
| GET | `/ai-pot/council` | 返回 council evaluations（含 agent_scores） |
| GET | `/ai-pot/sub-pots/{id}/pnl-history` | 返回单个 sub_pot 的 PnL 历史 |
| GET | `/ai-pot/raw` | 返回原始 API 数据（调试用） |

改 `GET /agents` 增加 council_score + council_rank
改 `GET /dashboard` 增强 pot 数据

### Phase 5: 前端

**修改文件：** `frontend/web/src/api/client.ts`, `App.tsx`, `Layout.tsx`
**新增文件：** `frontend/web/src/pages/AIPot.tsx`

1. 新建 `AIPot.tsx`（Summary / Sub-Pots / Council / Raw Data 四个 Tab）
2. AgentList 末尾追加 Council Score（紫色）+ Council Rank（#N）
3. Dashboard pot 卡片增强
4. 路由 `/ai-pot` + 导航栏

## 关键文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/db/models.py` | 修改+新增 | 新增 5 models, 增强 AIPotRound |
| `backend/db/database.py` | 修改+新增 | 新增 5 表 + 15+ CRUD 方法 |
| `backend/collectors/degenclaw_collector.py` | 重构 | AIPotCollector 接入真实 API |
| `backend/monitoring/pot_monitor.py` | 新增 | PnL 变化检测引擎 |
| `backend/scheduler/scheduler.py` | 修改 | run_collection() 增强 |
| `backend/config/settings.py` | 修改 | 新增 3 个 env var |
| `backend/api/routes.py` | 修改 | 新增 4 + 修改 2 端点 |
| `backend/notifiers/feishu_notifier.py` | 小改 | 新增 send_card() 通用方法 |
| `frontend/web/src/api/client.ts` | 修改 | 新增 types + fetch functions |
| `frontend/web/src/pages/AIPot.tsx` | 新增 | 完整 AIPot 页面 |
| `frontend/web/src/pages/AgentList.tsx` | 修改 | 追加 2 列 |
| `frontend/web/src/pages/Dashboard.tsx` | 修改 | 增强 pot cards |
| `frontend/web/src/App.tsx` | 修改 | 添加路由 |
| `frontend/web/src/components/Layout.tsx` | 修改 | 添加 nav item |

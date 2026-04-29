# Phase 0：信息调研与数据确认

## 概述

确认所有可用数据源，明确 DegenClaw、Agent Token、AI Pot、价格与流动性数据的获取路径。Phase 0 不写代码，只做调研和文档产出。

## 调研清单

### 1. DegenClaw 页面接口

- [ ] 定位 DegenClaw 页面 URL（virtuals.io 域名）
- [ ] 分析页面数据加载方式（SSR / Client Fetch / WebSocket）
- [ ] 如为 API：记录 endpoint、请求方式、参数、鉴权方式
- [ ] 如为页面抓取：评估 cheerio / puppeteer 可行性
- [ ] 评估请求频率限制
- [ ] 确认 leaderboard 分页方式

**产出字段确认：**
- Agent 列表（至少 top 50）
- 排名（current / previous）
- Agent 名称
- PnL（24h / 7d）
- Win rate
- Max drawdown
- Trade count

### 2. AI Pot 页面数据

- [ ] 定位 AI Pot 页面 URL
- [ ] 确认当前 round 信息获取方式
- [ ] 确认已选中 Agent 列表获取方式
- [ ] 确认 round 开始/结束时间
- [ ] 确认 AI Council 公布结果时间（PRD 提到周一）

### 3. Agent Profile 数据

- [ ] 确认 Agent 详情页 URL 结构（如 `/agent/{id}`）
- [ ] 确认 profile 包含字段
- [ ] 确认交易历史获取方式
- [ ] 确认 rationale 或策略描述获取方式

### 4. Agent Token 地址映射

- [ ] 确认 DegenClaw 页面是否直接显示 token 地址
- [ ] 如不直接显示：调研 Virtuals 平台 Agent Token 注册机制
- [ ] 确认 token 所在的 chain（Base？）
- [ ] 确认 token standard（ERC-20？）
- [ ] 确认 Agent Token 部署合约特征（可用来链上扫描）

### 5. 价格与流动性数据源

#### DexScreener API

- [ ] 确认 API endpoint（`https://api.dexscreener.com/latest/dex/...`）
- [ ] 确认 token 价格数据字段（priceUsd, liquidityUsd, volume, fdv）
- [ ] 确认支持的 chain
- [ ] 确认请求限制

#### Base RPC

- [ ] 确认 RPC URL（public / private）
- [ ] 确认需要的合约 ABI（ERC-20 基础 ABI）
- [ ] 是否需要 archive node
- [ ] 评估 RPC 请求频率限制

#### Codex API / GeckoTerminal API

- [ ] 确认可用 endpoint
- [ ] 确认返回字段
- [ ] 确认是否需要 API key

### 6. Virtuals Token Pool 数据

- [ ] 确认 Virtuals 平台 token 池数据暴露方式
- [ ] 确认 pool address 获取方式
- [ ] 确认 pool 中 token 数量与 USDC/WETH 数量

### 7. Holder 数据

- [ ] 确认 holder 数据获取方式（BaseScan API / RPC）
- [ ] 确认是否可获取 top 10 holder 占比
- [ ] 确认 holder 数据更新频率限制

## 产出文档

### 数据源清单

每条数据源记录以下信息：

| 字段 | 说明 |
|------|------|
| 数据源名称 | 如 DegenClaw Leaderboard |
| URL / Endpoint | 完整 URL 或 API endpoint |
| 请求方式 | GET / POST / WebSocket |
| 鉴权方式 | None / API Key / Bearer |
| 返回格式 | JSON / HTML |
| 频率限制 | 如 30 req/min |
| 数据字段 | 可用字段列表 |
| 稳定性评估 | 高/中/低 |
| 回退方案 | 如主源不可用时 |

### 字段说明文档

每个核心数据对象的字段定义：

- Agent 对象
- Token 对象
- Market Snapshot 对象
- AI Council Result 对象

### 接口可用性报告

- 每个接口的实测结果（可达、返回格式、延迟）
- 是否可以替代方案
- 推荐的主数据源和备用数据源

### 数据库 Schema 草案

基于调研结果，确认 PRD 中 schema 草案是否可行，调整字段类型和约束。

schema 设计原则：

- 所有快照表使用 snapshot_at 作为时间索引
- agent_id 和 token_address 作为核心关联键
- 价格使用 REAL 类型，金额使用 REAL，百分比使用 REAL
- 所有表包含 id 自增主键和 created_at

## 验收标准

- [ ] 至少能够稳定获取 top 50 Agent
- [ ] 至少能够将 Agent 与对应 token 地址关联
- [ ] 至少能够获取 token price、volume、liquidity
- [ ] 至少能够定时保存快照
- [ ] 所有数据源的频率限制已明确
- [ ] 每个数据源已确认备选方案

## 可交付物

```
docs/
├── DATA-SOURCES.md    # 最终版数据源清单
├── FIELDS.md          # 字段说明文档
├── API-REPORT.md      # 接口可用性报告
└── SCHEMA-V0.md       # 第一版 schema 草案
```

## 下一步

Phase 0 完成后进入 Phase 1：搭建项目骨架、数据库、采集服务基础框架。

# Phase 0: 信息调研与数据确认 — 执行清单

> 预估工期：3-5 天

## 1. DegenClaw 页面接口调研

- [x] 定位 DegenClaw 页面 URL（`https://app.virtuals.io/degenclaw`，React SPA）
- [x] 分析页面数据加载方式（Client Fetch API，非 SSR / WebSocket）
- [x] 如为 API：记录 endpoint、请求方式、参数、鉴权方式（见 DATA-SOURCES.md）
- [ ] 如为页面抓取：评估 cheerio / puppeteer 可行性（不必要，API 可用）
- [x] 评估请求频率限制（未限制，15 req/s 测试通过）
- [x] 确认 leaderboard 分页方式（Virtuals API 支持 `pagination[page]` + `pagination[pageSize]`）
- [x] 确认返回字段：agent 列表、名称、token 地址、流动性、成交量、持有人等

## 2. AI Pot 页面数据调研

- [ ] 定位 AI Pot 页面 URL（需要 claw-api auth 后测试）
- [ ] 确认当前 round 信息获取方式（需要 claw-api auth）
- [ ] 确认已选中 Agent 列表获取方式（需要 claw-api auth）
- [ ] 确认 round 开始/结束时间字段（需要 claw-api auth）
- [ ] 确认 AI Council 公布结果时间（PRD 提到周一）
- [ ] 确认 AI Pot PnL 数据是否可获取（需要 claw-api auth）

## 3. Agent Profile 数据调研

- [x] 确认 Agent 详情页 URL 结构（如 `https://app.virtuals.io/virtuals/{id}`）
- [x] 确认 profile 包含字段（name, symbol, description, creator, category 等，详见 FIELDS.md）
- [ ] 确认交易历史获取方式（可能来自 claw-api 或链上扫描）
- [ ] 确认 rationale / 策略描述是否可获取

## 4. Agent Token 地址映射调研

- [x] 确认 DegenClaw 页面直接显示 token 地址（Virtuals API 返回 `tokenAddress` / `preToken`）
- [x] 如不直接显示：调研 Virtuals 平台 Agent Token 注册机制（已确认 preToken → tokenAddress 迁移模式）
- [x] 确认 token 所在的 chain（Base, chainId=8453）
- [x] 确认 token standard（ERC-20）
- [x] 确认 Agent Token 部署合约特征（BONDING_V5 factory 合约）

## 5. 价格与流动性数据源调研

- [x] 确认 DexScreener API endpoint 和返回字段（不可用，TLS error）
- [ ] 确认 DexScreener 支持的 chain 和请求限制（未测试，被网络屏蔽）
- [x] 确认 Base RPC URL（public / private）和频率限制（可用，OKX-Robot 已稳定运行）
- [ ] 确认 Codex API / GeckoTerminal API 可用性和字段（未测试——Virtuals API 已足够）
- [x] 对比各数据源，确定主数据源和备用方案（主：Virtuals API，备：不需要）

## 6. 其他数据调研

- [x] 确认 Virtuals 平台 token pool 数据暴露方式（通过 Virtuals API 的 liquidityUsd 字段）
- [x] 确认 holder 数据获取方式（Virtuals API 直接提供 holderCount + top10HolderPercentage）
- [x] 确认 top 10 holder 占比是否可计算（API 直接返回）
- [x] 确认 SignalHub (004) 现有 sources/parsers 模块是否可直接复用
  - `sources/virtuals_source.py` — ✅ 可复用，直接 import
  - `parsers/virtuals_parser.py` — ✅ 可复用，直接 import
  - `scoring/score_engine.py` — ⚠️ 结构可参考，需重写评分维度
  - `lifecycle/lifecycle_engine.py` — ✅ 渐进式状态机模式可参考
  - `database/db.py` / `models.py` — ✅ 代码风格可参考
- [x] 确认 OKX-Robot (015) 现有 executor/okx_client 版本是否可用
  - `executor/okx_client.py` — ✅ 可直接 import，OKX DEX API 封装完善
  - `executor/trader.py` — ✅ 可直接 import，包含完整 swap 执行流
  - `risk/guard.py` (DailyLossGuard) — ✅ 可直接复用
  - `risk/take_profit.py` (TakeProfitMonitor) — ✅ 可直接复用
  - `db/database.py` — ✅ SQLite + aiosqlite 模式可参考
  - `config/loader.py` — ✅ YAML + .env 模式可参考

## 7. 产出文档

- [x] 整理数据源清单（endpoint、字段、频率限制、鉴权方式）→ `docs/DATA-SOURCES.md`
- [x] 编写字段说明文档 → `docs/FIELDS.md`
- [x] 编写接口可用性报告（可达性、延迟、稳定性）→ `docs/API-REPORT.md`
- [x] 确认第一版数据库 schema 草案 → `docs/SCHEMA-V0.md`

## 验收标准

- [x] 至少能够稳定获取 top 50 Agent（Virtuals API 支持全量分页）
- [x] 至少能够将 Agent 与对应 token 地址关联（`tokenAddress` / `preToken` 字段）
- [x] 至少能够获取 token price、volume、liquidity（`liquidityUsd`, `volume24h`, `priceChangePercent24h`）
- [x] 至少能够定时保存快照（market_snapshots 表设计完成）
- [ ] 所有数据源的频率限制已明确（DexScreener/CoinGecko 被网络屏蔽；Virtuals API 未发现限制）
- [x] 每个数据源已确认备选方案

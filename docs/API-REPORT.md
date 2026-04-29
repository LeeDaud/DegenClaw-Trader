# 接口可用性报告

> 实测结果：2026-04-28

---

## 1. Virtuals API（api2.virtuals.io）

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 可达 |
| 响应时间 | ~500ms-1.5s（首次），后续分页 ~200-500ms |
| 返回格式 | JSON（Strapi CMS 标准格式） |
| 实测端点 | `GET /api/virtuals` 返回 `{ data: [...], meta: { pagination: {...} } }` |
| 分页能力 | ✅ `pagination[page]` + `pagination[pageSize]` |
| 排序能力 | 部分字段支持 `sort=field:asc/desc`（如 `createdAt`, `launchedAt`；`rank` 不支持） |
| 过滤能力 | `filters[field][$operator]=value` 语法 |
| 频率限制 | 未遇到限流（15 req/s 测试通过） |
| 稳定性 | 高 — 生产环境，Virtuals 官方运维 |
| 数据量 | ~39,900 条总记录，13,303 页（pageSize=3 时） |

**综合评价：✅ 主数据源，建议在 Phase 1 直接复用 SignalHub 的 `VirtualsSource` 类。**

---

## 2. DegenClaw API（claw-api.virtuals.io）

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 可达 |
| 未鉴权响应 | 401 `Missing or invalid Authorization header` |
| 鉴权后 | 未测试（需要 JWT） |
| 健康检查 | ✅ `/health` 公开可达 |
| 已知端点 | `/agents`, `/agents/leaderboard`, `/agents/top`, `/agents/rankings`, `/agents/competition` |

**综合评价：⚠️ 需要解决 JWT 鉴权。核心排名数据在此。Phase 1-2 可先用 Virtuals API 替代。**

### 鉴权调研方向

1. **Privy 登录流程：** Virtuals 使用 Privy (privy.io) 做钱包登录。需研究 Privy API 是否可以程序化获取 token
2. **Cookie/Session 复用：** 手动登录后导出 JWT token，在服务端配置
3. **服务端模拟登录：** 使用 Privy SDK 或直接调用 Privy API

---

## 3. ACP API（acp-api.virtuals.io）

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 可达 |
| 健康检查 | ✅ `/health` 返回 200 |
| Agent 端点 | `/agents` 返回 401（需鉴权） |

**综合评价：⚠️ 与 claw-api 类似的鉴权要求，非优先级数据源。**

---

## 4. OKX DEX Aggregator API

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 确认可用（OKX-Robot 已稳定运行） |
| 鉴权方式 | HMAC-SHA256 签名 |
| 稳定性 | 高 |
| 复用评估 | ✅ `015-OKX-Robot/src/executor/okx_client.py` 可直接 import 使用 |

**综合评价：✅ 交易执行主数据源，Phase 4 直接复用 OKX-Robot 的 `OKXDexClient` 和 `Trader`。**

---

## 5. Base RPC

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 确认可用（OKX-Robot 已稳定运行） |
| 复用评估 | ✅ OKX-Robot 已有完整 RPC 交互代码 |

**综合评价：✅ 作为 OKX API 的补充和备用。**

---

## 6. BaseScan API

| 项目 | 结果 |
|------|------|
| 可达性 | ✅ 可达 |
| 响应 | 返回正常（V1 已弃用，需使用 V2 endpoint） |
| V2 endpoint | `https://api.basescan.org/api/v2` |
| 鉴权 | 需要 API Key（免费） |

**综合评价：✅ 可选数据源，用于 holder 详情分析。**

---

## 7. DexScreener API ❌

| 项目 | 结果 |
|------|------|
| 可达性 | ❌ TLS 连接失败（exit code 35） |
| 原因 | 企业网络屏蔽 |
| 影响 | 低 — Virtuals API 已提供 liquidityUsd、volume24h 等核心数据 |

**综合评价：❌ 不可用，且无需替代方案。**

---

## 8. CoinGecko API ❌

| 项目 | 结果 |
|------|------|
| 可达性 | ❌ 请求超时/无响应 |
| 原因 | 企业网络屏蔽 |

**综合评价：❌ 不可用，且无需替代方案（Virtuals API 足够）。**

---

## 数据源可用性总结

| 数据源 | Phase 1 | Phase 2 | Phase 3 | Phase 4-5 | Phase 6 |
|--------|---------|---------|---------|-----------|---------|
| Virtuals API | ✅ 主线 | ✅ 主线 | ✅ 支线 | ✅ 支线 | ✅ 支线 |
| DegenClaw API | ⚠️ 待 auth | ⚠️ 待 auth | ⚠️ 待 auth | ⚠️ 待 auth | ⚠️ 待 auth |
| OKX DEX API | — | — | — | ✅ 主线 | — |
| Base RPC | — | — | — | ✅ 支线 | — |
| BaseScan API | ⚠️ 可选 | ⚠️ 可选 | — | — | — |

---

## 推荐架构

```
Phase 1 (Monitoring MVP)
  └── Virtuals API (Primary) — no auth needed, all market data available

Phase 2 (Scoring MVP)
  ├── Virtuals API — market quality, holder data
  └── DegenClaw API — ranking data (after auth resolved)

Phase 3 (Signal MVP)
  └── Phase 1 + Phase 2 data + Decision Engine

Phase 4 (Semi-Auto Trading)
  ├── OKX DEX API — via OKX-Robot reuse
  └── Base RPC — on-chain validation

Phase 5 (Auto Trading)
  ├── OKX-Robot Risk — DailyLossGuard, TakeProfitMonitor
  └── OKX DEX API — via Trader reuse

Phase 6 (Optimization)
  └── All above + review engine
```

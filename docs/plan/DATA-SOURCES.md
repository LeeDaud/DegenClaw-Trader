# 数据源清单

## 1. Virtuals API（主要数据源）

### 1.1 Agent 列表 / 市场数据

| 属性 | 值 |
|------|-----|
| URL | `https://api2.virtuals.io/api/virtuals` |
| 请求方式 | GET |
| 鉴权方式 | 无（Public） |
| 返回格式 | JSON |
| 频率限制 | 未公开（实测 15 个/秒无阻断） |
| 分页 | `pagination[page]` + `pagination[pageSize]` |
| 排序 | `sort=createdAt:desc`（various fields） |
| 过滤 | `filters[field][$operator]=value` |
| 稳定性 | 高（生产环境，长期稳定） |
| 回退方案 | 无（唯一 Virtuals Agent 数据源） |

**可用字段：**
```
id, uid, name, symbol, status, description, category
tokenAddress, preToken, preTokenPair, lpAddress
liquidityUsd, volume24h, netVolume24h, priceChangePercent24h
holderCount, top10HolderPercentage, holderCountPercent24h
mcapInVirtual, fdvInVirtual, totalSupply
chain, level, valueFx
launchedAt, createdAt
acpAgentId, v3AcpAgentId
factory, totalValueLocked, virtualTokenValue
creator, image, cores
```

### 1.2 Agent 详情

| 属性 | 值 |
|------|-----|
| URL | `https://api2.virtuals.io/api/virtuals/{id}` |
| 请求方式 | GET |
| 鉴权方式 | 无（Public） |

**备注：** `populate=image,creator` 参数可展开关联数据。

## 2. DegenClaw API（排名与竞赛数据）

### 2.1 已知 Endpoints

| Endpoint | 说明 | 鉴权 |
|----------|------|------|
| `https://claw-api.virtuals.io/health` | 健康检查 | 无 |
| `https://claw-api.virtuals.io/agents` | Agent 列表 | Bearer JWT |
| `https://claw-api.virtuals.io/agents/leaderboard` | 排行榜 | Bearer JWT |
| `https://claw-api.virtuals.io/agents/top` | Top Agents | Bearer JWT |
| `https://claw-api.virtuals.io/agents/rankings` | 排名数据 | Bearer JWT |
| `https://claw-api.virtuals.io/agents/competition` | 竞赛数据 | Bearer JWT |

### 2.2 鉴权机制

- **类型：** Bearer JWT（Privy-based）
- **获取方式：** 用户通过 Privy 登录 app.virtuals.io 后，浏览器存储中持有 JWT token
- **状态：** ❌ 未解决（需要研究模拟登录或 Privy API 集成方案）

### 2.3 回退方案

- 使用 Virtuals API 获取基础 Agent 数据
- 排名数据暂缺（需要 claw-api auth 解决方案）

## 3. ACP API（Agent 性能数据）

### 3.1 已知 Endpoints

| Endpoint | 说明 | 鉴权 |
|----------|------|------|
| `https://acp-api.virtuals.io/health` | 健康检查 | 无 |
| `https://acp-api.virtuals.io/agents` | Agent 列表 | Bearer JWT |
| `https://acp-api.virtuals.io/agents/{id}` | Agent 详情 | Bearer JWT |

**备注：** ACP(AI Companion) 和 ACPX API 的 agents 端点也需要鉴权。

## 4. OKX DEX Aggregator API（交易执行）

| 属性 | 值 |
|------|-----|
| URL | `https://www.okx.com` |
| 请求方式 | GET |
| 鉴权方式 | HMAC-SHA256 Signature |
| 返回格式 | JSON |
| Chain ID | 8453（Base） |
| 频率限制 | 未知（OKX 标准 API 限制） |
| 稳定性 | 高 |
| 回退方案 | 直接 RPC swap |
| 复用来源 | `015-OKX-Robot` - `executor/okx_client.py` |

**可用接口：**
- `/api/v6/dex/aggregator/quote` — 获取报价
- `/api/v6/dex/aggregator/swap` — 构建 swap 交易

## 5. Base RPC（链上数据）

### 5.1 配置

| 属性 | 值 |
|------|-----|
| Chain ID | 8453 |
| RPC 类型 | HTTPS / WebSocket |
| 鉴权方式 | 可能需 API Key（取决于节点服务商） |

### 5.2 用途

- 代币余额查询
- 链上交易确认
- Token 池数据查询
- Honeypot 检测

### 5.3 回退方案

- OKX DEX API 内部已使用 Base RPC 数据
- 多数链上查询可通过 OKX API 间接获取

## 6. BaseScan API（链上数据）

| 属性 | 值 |
|------|-----|
| URL | `https://api.basescan.org/api/v2`（Etherscan V2） |
| 请求方式 | GET |
| 鉴权方式 | API Key（免费注册） |
| 稳定性 | 高 |

**用途：**
- Token holder 列表
- Holder 分布统计
- 交易历史查询
- Top 10 holder 占比计算

## 7. DexScreener API ❌（不可用）

| 属性 | 值 |
|------|-----|
| URL | `https://api.dexscreener.com/latest/dex/...` |
| 状态 | ❌ TLS 连接失败（exit code 35） |
| 原因 | 企业网络屏蔽 |
| 回退方案 | Virtuals API 已有足够数据 |

## 8. CoinGecko API ❌（不可用）

| 属性 | 值 |
|------|-----|
| URL | `https://api.coingecko.com/api/v3/...` |
| 状态 | ❌ 无响应（网络屏蔽） |
| 回退方案 | Virtuals API 提供 USD 计价数据 |

## 数据源依赖关系

```
Virtuals API (api2.virtuals.io)
  ├── Agent 列表 + 基础信息
  ├── Token 地址映射
  ├── 市场数据（流动性、成交量、价格变化）
  └── Holder 数据（holderCount, top10HolderPercentage）
       └── BaseScan API（holder 详情，可选）

DegenClaw API (claw-api.virtuals.io)  [待解决鉴权]
  └── 排名 / Leaderboard / 竞赛数据

OKX DEX API
  └── 交易执行（报价、swap）

Base RPC / WebSocket
  └── 链上数据验证
```

## 小结

| 需求 | 状态 | 数据源 |
|------|------|--------|
| Agent 基本信息 | ✅ 可用 | Virtuals API |
| Token 地址 | ✅ 可用 | Virtuals API（tokenAddress / preToken） |
| Token 价格/流动性/成交量 | ✅ 可用 | Virtuals API |
| Holder 分布 | ✅ 可用 | Virtuals API（top10HolderPercentage） |
| DegenClaw 排名 | ❌ 待解决 | claw-api.virtuals.io（需 JWT） |
| 交易执行 | ✅ 可用 | OKX DEX API（OKX-Robot 复用） |
| 链上数据 | ✅ 可用 | Base RPC + BaseScan |
| USD 价格替代 | ✅ 无需 | Virtuals API 已有 liquidityUsd |

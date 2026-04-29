"""Phase 1 模拟数据 — 采集器使用"""

# 第一组 Top 10 — 有明确趋势变化的 Agent
# agent_011 排名从 15→11，3 轮持续上升（看涨）
# agent_012 排名从 8→14，3 轮持续下跌（看跌）
# agent_013 收益从 5.2% 暴涨到 18.7%（大涨）
# agent_014 收益从 3.1% 暴跌到 -12.5%（大跌）
# agent_015 排名 7→6→3，上升+收益改善（综合看涨）

MOCK_AGENTS = [
    {"id": "agent_001", "name": "AlphaXTrader", "rank": 1, "pnl_24h": 12.5, "pnl_7d": 45.2,
     "win_rate": 68.0, "max_drawdown": -8.5, "trade_count": 342, "is_top_10": True,
     "is_selected": True, "token_address": "0x0000000000000000000000000000000000000001"},
    {"id": "agent_002", "name": "BetaMomentum", "rank": 2, "pnl_24h": 8.3, "pnl_7d": 32.1,
     "win_rate": 72.0, "max_drawdown": -6.2, "trade_count": 287, "is_top_10": True,
     "is_selected": True, "token_address": "0x0000000000000000000000000000000000000002"},
    {"id": "agent_003", "name": "GammaArbitrage", "rank": 3, "pnl_24h": -2.1, "pnl_7d": 18.7,
     "win_rate": 55.0, "max_drawdown": -12.0, "trade_count": 156, "is_top_10": True,
     "is_selected": True, "token_address": "0x0000000000000000000000000000000000000003"},
    {"id": "agent_004", "name": "DeltaScalper", "rank": 4, "pnl_24h": 5.6, "pnl_7d": 28.3,
     "win_rate": 65.0, "max_drawdown": -5.8, "trade_count": 423, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000004"},
    {"id": "agent_005", "name": "EpsilonTrend", "rank": 5, "pnl_24h": 3.2, "pnl_7d": 15.0,
     "win_rate": 60.0, "max_drawdown": -9.1, "trade_count": 198, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000005"},
    {"id": "agent_006", "name": "ZetaHedge", "rank": 6, "pnl_24h": -1.8, "pnl_7d": 8.9,
     "win_rate": 52.0, "max_drawdown": -15.3, "trade_count": 265, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000006"},
    {"id": "agent_007", "name": "EtaVolMaster", "rank": 7, "pnl_24h": 10.1, "pnl_7d": 38.6,
     "win_rate": 70.0, "max_drawdown": -7.2, "trade_count": 312, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000007"},
    {"id": "agent_008", "name": "ThetaBreakout", "rank": 8, "pnl_24h": 6.7, "pnl_7d": 22.4,
     "win_rate": 63.0, "max_drawdown": -10.5, "trade_count": 178, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000008"},
    {"id": "agent_009", "name": "IotaLiquid", "rank": 9, "pnl_24h": -4.2, "pnl_7d": 5.3,
     "win_rate": 48.0, "max_drawdown": -18.0, "trade_count": 145, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000009"},
    {"id": "agent_010", "name": "KappaReversal", "rank": 10, "pnl_24h": 2.9, "pnl_7d": 12.8,
     "win_rate": 58.0, "max_drawdown": -11.2, "trade_count": 201, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000010"},
    # 趋势变化信号 Agent
    {"id": "agent_011", "name": "LambdaSurge", "rank": 11, "pnl_24h": 18.7, "pnl_7d": 52.3,
     "win_rate": 76.0, "max_drawdown": -4.2, "trade_count": 189, "is_top_10": False,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000011"},
    {"id": "agent_012", "name": "MuDump", "rank": 14, "pnl_24h": -12.5, "pnl_7d": -8.3,
     "win_rate": 38.0, "max_drawdown": -22.5, "trade_count": 312, "is_top_10": False,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000012"},
    {"id": "agent_013", "name": "NuRocket", "rank": 16, "pnl_24h": 22.4, "pnl_7d": 68.1,
     "win_rate": 80.0, "max_drawdown": -3.1, "trade_count": 98, "is_top_10": False,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000013"},
    {"id": "agent_014", "name": "XiPlunge", "rank": 42, "pnl_24h": -18.2, "pnl_7d": -35.6,
     "win_rate": 28.0, "max_drawdown": -35.0, "trade_count": 178, "is_top_10": False,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000014"},
    {"id": "agent_015", "name": "OmicronRise", "rank": 3, "pnl_24h": 15.3, "pnl_7d": 42.8,
     "win_rate": 74.0, "max_drawdown": -5.5, "trade_count": 256, "is_top_10": True,
     "is_selected": False, "token_address": "0x0000000000000000000000000000000000000015"},
]

MOCK_AGENTS_16_50 = [
    {"id": f"agent_{i:03d}", "name": f"DegenAgent{i}", "rank": i,
     "pnl_24h": round(5.0 - i * 0.3 + 2.0, 1), "pnl_7d": round(30.0 - i * 0.6, 1),
     "win_rate": round(60.0 - i * 0.4, 1), "max_drawdown": round(-5.0 - i * 0.3, 1),
     "trade_count": 200 - i, "is_top_10": False, "is_selected": False,
     "token_address": f"0x{i:040d}"}
    for i in range(16, 51)
]

MOCK_TOKENS = [
    {"token_address": "0x0000000000000000000000000000000000000001", "symbol": "AXP", "name": "AlphaX Token",
     "pool_address": "0x1000000000000000000000000000000000000001", "chain": "base",
     "price_usd": 0.42, "liquidity_usd": 120000, "volume_1h": 5200, "volume_24h": 45000,
     "price_change_1h": 2.1, "price_change_24h": 35.0, "buy_slippage": 1.2, "sell_slippage": 1.8,
     "holder_count": 342, "top_10_holder_pct": 28.5},
    {"token_address": "0x0000000000000000000000000000000000000002", "symbol": "BMT", "name": "Beta Momentum Token",
     "pool_address": "0x1000000000000000000000000000000000000002", "chain": "base",
     "price_usd": 1.23, "liquidity_usd": 85000, "volume_1h": 3100, "volume_24h": 22000,
     "price_change_1h": -0.5, "price_change_24h": 12.0, "buy_slippage": 2.1, "sell_slippage": 2.8,
     "holder_count": 215, "top_10_holder_pct": 35.2},
]


def get_mock_agents() -> list[dict]:
    return MOCK_AGENTS + MOCK_AGENTS_16_50


def get_mock_token(address: str) -> dict | None:
    for t in MOCK_TOKENS:
        if t["token_address"].lower() == address.lower():
            return t
    return None


def get_mock_token_by_symbol(symbol: str) -> dict | None:
    for t in MOCK_TOKENS:
        if t["symbol"].lower() == symbol.lower():
            return t
    return None

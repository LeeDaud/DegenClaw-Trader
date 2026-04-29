from __future__ import annotations

import asyncio
from typing import Any

import httpx

from collectors.mock_data import get_mock_agents
from config.settings import Settings
from db.models import utc_now_iso


def _normalize_degenclaw_item(item: dict[str, Any], rank: int) -> dict[str, Any]:
    """DegenClaw leaderboard API → 内部字段映射"""
    perf = item.get("performance") or {}
    return {
        "id": str(item.get("id", "")),
        "name": item.get("name", ""),
        "token_address": item.get("tokenAddress", ""),
        "agent_address": item.get("agentAddress", ""),
        "token_symbol": item.get("tokenSymbol", ""),
        "virtual_id": item.get("virtualId"),
        "image_url": item.get("imageUrl", ""),
        "rank": rank,
        "pnl_24h": 0.0,
        "pnl_7d": round(float(perf.get("returnPct", 0) or 0) * 100, 2),
        "win_rate": round(float(perf.get("winRate", 0) or 0) * 100, 1),
        "max_drawdown": 0.0,
        "trade_count": int(perf.get("totalTradeCount", 0) or 0),
        "total_realized_pnl": float(perf.get("totalRealizedPnl", 0) or 0),
        "holdings_value_usd": float(perf.get("holdingsValueUsd", 0) or 0),
        "total_trade_volume": float(perf.get("totalTradeVolume", 0) or 0),
        "is_top_10": rank <= 10,
        "is_selected": False,
    }


class DegenClawCollector:
    """DegenClaw 排行榜采集器 — 对接 degen.virtuals.io/api/leaderboard"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._is_mock = settings.collector_source == "mock"

    async def fetch_leaderboard(self) -> list[dict[str, Any]]:
        if self._is_mock:
            return get_mock_agents()

        if not self.settings.degenclaw_endpoint:
            return []

        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "accept": "application/json, text/plain, */*",
        }

        limit = 50
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            tasks = [
                self._fetch_offset_page(client, offset)
                for offset in range(0, self.settings.virtuals_max_pages * limit, limit)
            ]
            page_results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items: list[dict[str, Any]] = []
        for result in page_results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, list):
                all_items.extend(result)

        if not all_items:
            return []

        # 已按排名排序（API 返回顺序即为排名），分配 rank
        normalized = []
        for idx, item in enumerate(all_items, start=1):
            normalized.append(_normalize_degenclaw_item(item, idx))

        return normalized

    async def _fetch_offset_page(self, client: httpx.AsyncClient, offset: int) -> list[dict[str, Any]]:
        """抓取一页（50 条）"""
        params = {"limit": 50, "offset": offset}
        response = await client.get(self.settings.degenclaw_endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        return items

    async def fetch_agent_detail(self, agent_id: str) -> dict[str, Any] | None:
        if self._is_mock:
            for agent in get_mock_agents():
                if agent["id"] == agent_id:
                    return agent
            return None

        if not self.settings.degenclaw_endpoint:
            return None

        headers = self._build_headers()
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
            follow_redirects=True,
        ) as client:
            response = await client.get(f"{self.settings.degenclaw_endpoint}/{agent_id}")
            response.raise_for_status()
            payload = response.json()
            return payload.get("data", payload)

    def _build_headers(self) -> dict[str, str]:
        return {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "referer": "https://degen.virtuals.io/",
            "origin": "https://degen.virtuals.io",
            "accept": "application/json, text/plain, */*",
        }


class MarketCollector:
    """市场数据采集器 (DexScreener)"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._is_mock = settings.collector_source == "mock"

    async def fetch_token_data(self, token_address: str) -> dict[str, Any] | None:
        if self._is_mock:
            return self._mock_market_data(token_address)

        if not self.settings.dexscreener_endpoint:
            return None

        headers = {"user-agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.get(
                f"{self.settings.dexscreener_endpoint}/tokens/{token_address}",
            )
            response.raise_for_status()
            payload = response.json()
        pairs = payload.get("pairs", [])
        if not pairs:
            return None
        pair = pairs[0]
        return {
            "token_address": token_address,
            "price_usd": float(pair.get("priceUsd", 0)),
            "liquidity_usd": float(pair.get("liquidity", {}).get("usd", 0)),
            "volume_1h": float(pair.get("volume", {}).get("h24", 0)) / 24 if pair.get("volume") else 0,
            "volume_24h": float(pair.get("volume", {}).get("h24", 0)),
            "price_change_1h": float(pair.get("priceChange", {}).get("h1", 0)),
            "price_change_24h": float(pair.get("priceChange", {}).get("h24", 0)),
            "buy_slippage": 0.0,
            "sell_slippage": 0.0,
            "holder_count": 0,
            "top_10_holder_pct": 0.0,
            "pool_address": pair.get("pairAddress", ""),
            "chain": pair.get("chainId", "base"),
        }

    async def fetch_batch(self, addresses: list[str]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for addr in addresses:
            data = await self.fetch_token_data(addr)
            if data:
                results.append(data)
        return results

    def _mock_market_data(self, token_address: str) -> dict[str, Any] | None:
        from collectors.mock_data import get_mock_token

        token = get_mock_token(token_address)
        if token:
            return {
                "token_address": token["token_address"],
                "symbol": token["symbol"],
                "name": token["name"],
                "price_usd": token["price_usd"],
                "liquidity_usd": token["liquidity_usd"],
                "volume_1h": token["volume_1h"],
                "volume_24h": token["volume_24h"],
                "price_change_1h": token["price_change_1h"],
                "price_change_24h": token["price_change_24h"],
                "buy_slippage": token["buy_slippage"],
                "sell_slippage": token["sell_slippage"],
                "holder_count": token["holder_count"],
                "top_10_holder_pct": token["top_10_holder_pct"],
                "pool_address": token["pool_address"],
                "chain": token["chain"],
            }
        return None


class AIPotCollector:
    """AI Pot 状态采集器"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._is_mock = settings.collector_source == "mock"

    async def fetch_pot_status(self) -> dict[str, Any] | None:
        if self._is_mock:
            return {
                "round_id": "round_001",
                "round_start": "2026-04-21T00:00:00Z",
                "round_end": "2026-04-28T00:00:00Z",
                "status": "active",
                "selected_agents": ["agent_001", "agent_002", "agent_003"],
                "pot_pnl": 12.5,
            }
        return None

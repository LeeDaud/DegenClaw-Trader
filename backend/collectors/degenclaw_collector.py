from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from collectors.mock_data import get_mock_agents
from config.settings import Settings
from db.models import utc_now_iso

logger = logging.getLogger(__name__)


def _normalize_degenclaw_item(item: dict[str, Any], position: int) -> dict[str, Any]:
    """DegenClaw leaderboard API → 内部字段映射"""
    perf = item.get("performance") or {}
    # 优先用 API 返回的 rank 字段，没有则用位置索引
    rank = int(item["rank"]) if "rank" in item else position
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
        "last_trade_at": perf.get("lastTradeAt", ""),
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

        # API 按 returnPct 降序返回，用数组位置作为排名兜底
        normalized = []
        for pos, item in enumerate(all_items, start=1):
            normalized.append(_normalize_degenclaw_item(item, pos))

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
    """AI Pot 状态采集器 — 对接 degen.virtuals.io/api/pot-agents 和 /api/council"""

    POT_AGENTS_API = "https://degen.virtuals.io/api/pot-agents"
    COUNCIL_API = "https://degen.virtuals.io/api/council"
    COUNCIL_API_SEASONS = "https://degen.virtuals.io/api/council/seasons"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._is_mock = settings.collector_source == "mock"

    async def fetch_pot_status(self) -> dict[str, Any] | None:
        """主入口：返回合并的 pot 状态（含 sub_pots 和 council_data）"""
        if self._is_mock:
            return self._mock_pot_status()

        pot_agents = await self._fetch_pot_agents()
        if not pot_agents:
            return None

        # 提取赛季信息
        first = pot_agents[0]
        cs = first.get("currentSeason") or {}
        season_id = cs.get("seasonId", "")
        season_name = cs.get("seasonName", "")

        # 计算汇总数据
        sub_pots_norm = [self._normalize_sub_pot(a) for a in pot_agents]
        total_capital = sum(s["starting_capital"] for s in sub_pots_norm)
        total_value = sum(s["current_value"] for s in sub_pots_norm)
        total_realized = sum(s["realized_pnl"] for s in sub_pots_norm)
        total_unrealized = sum(s["unrealized_pnl"] for s in sub_pots_norm)
        total_final = sum(s["final_pnl"] for s in sub_pots_norm)
        return_pct = round((total_value / total_capital - 1) * 100, 2) if total_capital else 0.0

        # 尝试获取评委会数据
        council_data = await self._fetch_council_for_season(season_id)

        now = utc_now_iso()
        return {
            "round_id": f"pot_{season_id}",
            "round_start": cs.get("seasonStartDate", now),
            "round_end": cs.get("seasonEndDate", now),
            "status": "active",
            "selected_agents": json.dumps([s["name"] for s in sub_pots_norm]),
            "pot_pnl": total_final,
            "season_id": season_id,
            "season_name": season_name,
            "total_capital": total_capital,
            "total_current_value": total_value,
            "total_realized_pnl": total_realized,
            "total_unrealized_pnl": total_unrealized,
            "return_pct": return_pct,
            "raw_data": json.dumps({"pot_agents": pot_agents, "council": council_data}, ensure_ascii=False),
            "sub_pots": sub_pots_norm,
            "council_data": council_data,
        }

    async def _fetch_pot_agents(self) -> list[dict[str, Any]] | None:
        """GET /api/pot-agents"""
        headers = _build_api_headers()
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                resp = await client.get(self.POT_AGENTS_API)
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data", [])
                return data if isinstance(data, list) else None
        except Exception as exc:
            logger.warning("fetch pot-agents failed: %s", exc)
            return None

    async def _fetch_council(self, season_id: str) -> dict[str, Any] | None:
        """GET /api/council?seasonId=N"""
        headers = _build_api_headers()
        try:
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                resp = await client.get(self.COUNCIL_API, params={"seasonId": season_id})
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("success"):
                    return payload.get("data")
                return None
        except Exception as exc:
            logger.warning("fetch council (seasonId=%s) failed: %s", season_id, exc)
            return None

    async def _fetch_council_seasons(self) -> list[int]:
        """GET /api/council/seasons — 返回可用的 council season ID 列表"""
        headers = _build_api_headers()
        try:
            async with httpx.AsyncClient(timeout=10, headers=headers) as client:
                resp = await client.get(self.COUNCIL_API_SEASONS)
                resp.raise_for_status()
                payload = resp.json()
                if payload.get("success"):
                    return payload.get("data", {}).get("seasons", [])
                return []
        except Exception:
            return []

    async def _fetch_council_for_season(self, pot_season_id: str) -> dict[str, Any] | None:
        """尝试找到匹配的评委会数据：先试 pot_season_id，再试最新 council season"""
        council = await self._fetch_council(pot_season_id)
        if council:
            return council
        # 遍历可用 council season（取最新的）
        seasons = await self._fetch_council_seasons()
        for sid in sorted(seasons, reverse=True):
            council = await self._fetch_council(str(sid))
            if council:
                return council
        return None

    def _normalize_sub_pot(self, item: dict[str, Any]) -> dict[str, Any]:
        """将 pot-agent API 项扁平化为内部字段"""
        cs = item.get("currentSeason") or {}
        starting_capital = float(cs.get("startingCapital", 0) or 0)
        final_pnl = float(cs.get("finalPnl", 0) or 0)
        api_current_value = float(cs.get("currentValue", 0) or 0)
        # API 偶发返回 currentValue=0，此时尝试推算
        if api_current_value == 0:
            if starting_capital + final_pnl != 0:
                current_value = max(0, starting_capital + final_pnl)
            else:
                # capital+finalPnl 也为 0，检查是否有开放持仓
                positions = cs.get("positions")
                if positions:
                    margin_sum = sum(
                        float(p.get("notionalSize", 0)) / max(float(p.get("leverage", 1)), 1)
                        for p in positions
                    )
                    current_value = max(0, round(margin_sum + starting_capital + final_pnl, 2))
                else:
                    current_value = 0.0
        else:
            current_value = api_current_value
        return {
            "sub_pot_id": str(item.get("id", "")),
            "name": item.get("name", ""),
            "status": item.get("status", "active"),
            "agent_id": str(cs.get("copyTradeAgentId", "")),
            "agent_name": cs.get("copyTradeAgentName", ""),
            "token_address": cs.get("tokenAddress", ""),
            "token_symbol": cs.get("tokenSymbol", ""),
            "starting_capital": starting_capital,
            "current_value": current_value,
            "realized_pnl": float(cs.get("realizedPnl", 0) or 0),
            "unrealized_pnl": float(cs.get("unrealizedPnl", 0) or 0),
            "final_pnl": final_pnl,
            "positions": json.dumps(cs.get("positions", [])),
        }

    async def fetch_raw_pot_agents(self) -> list[dict[str, Any]] | None:
        """返回原始 pot-agents API 数据（调试用）"""
        if self._is_mock:
            return []
        return await self._fetch_pot_agents()

    async def fetch_raw_council(self, season_id: str) -> dict[str, Any] | None:
        """返回原始 council API 数据（调试用）"""
        if self._is_mock:
            return None
        return await self._fetch_council(season_id)

    def _mock_pot_status(self) -> dict[str, Any]:
        now = utc_now_iso()
        mock_sub_pots = [
            {"sub_pot_id": "5", "name": "DiamondHands", "status": "ACTIVE",
             "agent_id": "210", "agent_name": "Degentic AI", "token_address": "", "token_symbol": "BL",
             "starting_capital": 39576, "current_value": 43312.43, "realized_pnl": 3736.43,
             "unrealized_pnl": 0, "final_pnl": 3736.43, "positions": "[]"},
            {"sub_pot_id": "4", "name": "GoldenHands", "status": "ACTIVE",
             "agent_id": "280", "agent_name": "BenYorke | Starchild", "token_address": "", "token_symbol": "BENYORKE",
             "starting_capital": 33922, "current_value": 33291.20, "realized_pnl": -630.80,
             "unrealized_pnl": 0, "final_pnl": -630.80, "positions": "[]"},
            {"sub_pot_id": "3", "name": "SilverHands", "status": "ACTIVE",
             "agent_id": "350", "agent_name": "seykota", "token_address": "", "token_symbol": "SEYKOTA",
             "starting_capital": 26148, "current_value": 28572.35, "realized_pnl": 2424.35,
             "unrealized_pnl": 0, "final_pnl": 2424.35, "positions": "[]"},
        ]
        total_capital = sum(s["starting_capital"] for s in mock_sub_pots)
        total_value = sum(s["current_value"] for s in mock_sub_pots)
        total_pnl = sum(s["final_pnl"] for s in mock_sub_pots)
        return_pct = round((total_value / total_capital - 1) * 100, 2) if total_capital else 0.0
        return {
            "round_id": "pot_mock",
            "round_start": now, "round_end": now,
            "status": "active",
            "selected_agents": json.dumps([s["name"] for s in mock_sub_pots]),
            "pot_pnl": total_pnl,
            "season_id": "mock",
            "season_name": "Mock Season",
            "total_capital": total_capital,
            "total_current_value": total_value,
            "total_realized_pnl": total_pnl,
            "total_unrealized_pnl": 0,
            "return_pct": return_pct,
            "raw_data": "{}",
            "sub_pots": mock_sub_pots,
            "council_data": None,
        }


def _build_api_headers() -> dict[str, str]:
    return {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "accept": "application/json, text/plain, */*",
        "referer": "https://degen.virtuals.io/",
    }

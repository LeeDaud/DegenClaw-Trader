"""高频价格采集器 — 独立于主采集周期，用于烛图反转分析"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from config.settings import Settings
from db.models import PriceTick, utc_now_iso

logger = logging.getLogger(__name__)

BATCH_MAX = 30  # DexScreener 批量接口最多 30 个地址


class PriceTicker:
    """高频采集所有 Agent token 的实时价格，写入 price_ticks 表"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._is_mock = settings.collector_source == "mock"
        # 缓存 token 地址列表（懒加载）
        self._cached_addresses: list[str] | None = None
        self._cache_time: float = 0.0

    def update_address_cache(self, addresses: list[str]) -> None:
        """外部调用方（run_collection）每次更新后刷新地址缓存"""
        self._cached_addresses = list(set(addresses))
        self._cache_time = __import__("time").time()

    async def tick(self) -> list[PriceTick]:
        """执行一轮采集，返回新的 PriceTick 列表"""
        if self._is_mock:
            return await self._mock_tick()

        addresses = self._cached_addresses or []
        if not addresses:
            return []

        ticks: list[PriceTick] = []
        now = utc_now_iso()

        # 优先批量接口
        if self.settings.dexscreener_endpoint:
            ticks = await self._fetch_batch(addresses, now)
        else:
            logger.warning("DexScreener endpoint not configured, skipping price tick")

        return ticks

    async def _fetch_batch(self, addresses: list[str], now: str) -> list[PriceTick]:
        """分批批量请求 DexScreener（30地址/批），降级到单地址"""
        ticks: list[PriceTick] = []
        seen: set[str] = set()

        # 分批（BATCH_MAX 个地址一批）
        for i in range(0, len(addresses), BATCH_MAX):
            batch = addresses[i:i + BATCH_MAX]
            batch_key = ",".join(batch)

            url = f"{self.settings.dexscreener_endpoint}/tokens/{batch_key}"
            try:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    resp = await client.get(url, headers={"user-agent": "Mozilla/5.0"})
                    resp.raise_for_status()
                    payload = resp.json()
            except Exception as exc:
                logger.warning("price tick batch failed (%d addrs), fallback to single: %s", len(batch), exc)
                # 降级到单地址逐个请求
                for addr in batch:
                    tick = await self._fetch_single(addr, now)
                    if tick:
                        ticks.append(tick)
                continue

            pairs = payload.get("pairs", [])
            if not pairs:
                continue

            # DexScreener batch 返回所有 pair，按 token_address 去重
            for pair in pairs:
                token_addr = pair.get("baseToken", {}).get("address", "")
                if not token_addr or token_addr in seen:
                    continue
                seen.add(token_addr)

                price_usd = float(pair.get("priceUsd", 0) or 0)
                vol_h24 = float(pair.get("volume", {}).get("h24", 0) or 0)
                volume_1h = vol_h24 / 24 if vol_h24 else 0.0

                ticks.append(PriceTick(
                    token_address=token_addr,
                    price_usd=price_usd,
                    volume_1h=volume_1h,
                    snapshot_at=now,
                ))

        return ticks

    async def _fetch_single(self, token_address: str, now: str) -> PriceTick | None:
        """单地址请求"""
        url = f"{self.settings.dexscreener_endpoint}/tokens/{token_address}"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                resp = await client.get(url, headers={"user-agent": "Mozilla/5.0"})
                resp.raise_for_status()
                payload = resp.json()
            pairs = payload.get("pairs", [])
            if not pairs:
                return None
            pair = pairs[0]
            price_usd = float(pair.get("priceUsd", 0) or 0)
            vol_h24 = float(pair.get("volume", {}).get("h24", 0) or 0)
            volume_1h = vol_h24 / 24 if vol_h24 else 0.0
            return PriceTick(
                token_address=token_address,
                price_usd=price_usd,
                volume_1h=volume_1h,
                snapshot_at=now,
            )
        except Exception as exc:
            logger.debug("price tick single failed %s: %s", token_address, exc)
            return None

    async def _mock_tick(self) -> list[PriceTick]:
        """Mock 模式下产生模拟 tick 数据"""
        from collectors.mock_data import get_mock_agents, get_mock_token

        now = utc_now_iso()
        ticks: list[PriceTick] = []
        for agent in get_mock_agents():
            addr = agent.get("token_address", "") or agent.get("tokenAddress", "")
            if not addr:
                continue
            mock_token = get_mock_token(addr)
            price_usd = mock_token["price_usd"] if mock_token else 1.0
            vol_h24 = mock_token["volume_24h"] if mock_token else 10000
            volume_1h = vol_h24 / 24
            ticks.append(PriceTick(
                token_address=addr,
                price_usd=price_usd,
                volume_1h=volume_1h,
                snapshot_at=now,
            ))
        return ticks

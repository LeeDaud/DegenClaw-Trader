"""DegenClaw 赛季管理器 — 获取当前赛季信息，过滤当季 Agent"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SEASONS_API = "https://degen.virtuals.io/api/seasons"
CACHE_SECONDS = 3600  # 赛季信息 1 小时缓存


@dataclass
class DegenSeason:
    season_id: str
    name: str
    start_date: str
    end_date: str
    is_active: bool

    @property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.start_date.replace("Z", "+00:00"))

    @property
    def end_dt(self) -> datetime:
        return datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))

    def contains(self, dt_str: str) -> bool:
        """判断某个时间戳是否在本赛季范围内"""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return self.start_dt <= dt <= self.end_dt
        except (ValueError, TypeError):
            return False


class SeasonManager:
    """赛季管理器：自动检测当前赛季，过滤非当季 Agent"""

    def __init__(self) -> None:
        self._current: DegenSeason | None = None
        self._last_fetch: datetime | None = None

    async def fetch_current_season(self) -> DegenSeason | None:
        """从 DegenClaw API 获取当前赛季"""
        now = datetime.now(timezone.utc)
        if self._current and self._last_fetch:
            if (now - self._last_fetch).total_seconds() < CACHE_SECONDS:
                return self._current

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(SEASONS_API, headers={
                    "user-agent": "Mozilla/5.0",
                    "accept": "application/json",
                })
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            logger.warning("fetch seasons failed: %s", exc)
            return self._current

        seasons_data = payload.get("data", [])
        for s in seasons_data:
            if s.get("isActive"):
                self._current = DegenSeason(
                    season_id=str(s["id"]),
                    name=s.get("name", ""),
                    start_date=s.get("startDate", ""),
                    end_date=s.get("endDate", ""),
                    is_active=True,
                )
                self._last_fetch = now
                logger.info("当前赛季: %s (%s ~ %s)",
                            self._current.name,
                            self._current.start_date[:10],
                            self._current.end_date[:10])
                return self._current

        logger.warning("no active season found")
        return None

from __future__ import annotations

import asyncio
import logging

from config.settings import Settings
from db.database import Database
from db.models import (
    LeaderboardSnapshot, SystemEvent, Token, build_event_id, utc_now_iso,
)
from collectors.degenclaw_collector import DegenClawCollector, MarketCollector, AIPotCollector
from notifiers.feishu_notifier import FeishuNotifier
from parsers.degenclaw_parser import DegenClawParser
from scoring.engine import DegenClawScoreEngine
from signals.signal_engine import SignalEngine

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ModuleNotFoundError:
    AsyncIOScheduler = None  # fallback handled below

logger = logging.getLogger(__name__)


async def run_collection(database: Database, settings: Settings) -> dict[str, int]:
    """执行一轮完整采集"""
    parser = DegenClawParser()
    degenclaw = DegenClawCollector(settings)
    market = MarketCollector(settings)
    pot = AIPotCollector(settings)
    trace_id = build_event_id()
    now = utc_now_iso()

    summary = {"agents": 0, "tokens": 0, "pot": 0}

    try:
        # 1. 采集 Agent 排行榜
        raw_agents = await degenclaw.fetch_leaderboard()
        agents, snapshots = parser.parse_leaderboard(raw_agents)

        for agent in agents:
            database.upsert_agent(agent)
        database.insert_agent_snapshots(snapshots)

        # 存原始快照
        import json
        database.insert_leaderboard_snapshot(LeaderboardSnapshot(
            snapshot_at=now,
            raw_data=json.dumps(raw_agents, ensure_ascii=False, default=str),
        ))

        summary["agents"] = len(agents)

        # 2. 采集 Token 市场数据
        token_addresses = [a.token_address for a in agents if a.token_address]
        if token_addresses:
            market_data = await market.fetch_batch(list(set(token_addresses)))
            market_snapshots = []
            for md in market_data:
                parsed = parser.parse_market_data(md)
                if parsed:
                    market_snapshots.append(parsed)
                    # 确保 token 存在
                    database.upsert_token(Token(
                        token_address=parsed.token_address,
                        symbol=md.get("symbol", ""),
                        name=md.get("name", ""),
                        pool_address=md.get("pool_address", ""),
                        chain=md.get("chain", "base"),
                        created_at=now,
                        updated_at=now,
                    ))
            database.insert_market_snapshots(market_snapshots)
            summary["tokens"] = len(market_snapshots)

        # 3. 采集 AI Pot 状态
        pot_status = await pot.fetch_pot_status()
        if pot_status:
            from db.models import AIPotRound
            database.upsert_ai_pot_round(AIPotRound(
                round_id=pot_status["round_id"],
                round_start=pot_status["round_start"],
                round_end=pot_status["round_end"],
                status=pot_status["status"],
                selected_agents=json.dumps(pot_status.get("selected_agents", [])),
                pot_pnl=float(pot_status.get("pot_pnl", 0)),
                created_at=now,
                updated_at=now,
            ))
            summary["pot"] = 1

        # 记录成功事件
        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="collector",
            level="info",
            event="collection_completed",
            detail=f"agents={summary['agents']} tokens={summary['tokens']} pot={summary['pot']}",
            trace_id=trace_id,
            created_at=now,
        ))

        # 4. 运行信号检测
        signal_engine = SignalEngine(database)
        new_alerts = signal_engine.run_check()
        if new_alerts:
            logger.info("信号检测完成: 生成 %d 条预警", len(new_alerts))

            # 飞书通知
            notifier = FeishuNotifier(settings.feishu_webhook_url)
            if settings.feishu_alerts_enabled and notifier.is_configured():
                alert_dicts = [a.as_record() for a in new_alerts]
                sent = notifier.send_alerts_batch(alert_dicts)
                # 标记已通知
                if sent > 0:
                    for alert in new_alerts:
                        database.mark_alert_notified(alert.alert_id)
                logger.info("飞书通知: 成功 %d / 总数 %d", sent, len(new_alerts))

            summary["alerts"] = len(new_alerts)

        # 5. 运行评分
        try:
            score_engine = DegenClawScoreEngine(database)
            score_results = score_engine.run_round()
            for score in score_results:
                database.insert_agent_score(score)
            summary["scored"] = len(score_results)
            logger.info("评分完成: %d 个 Agent", len(score_results))
        except Exception as exc:
            logger.exception("scoring failed: %s", exc)
            summary["scored"] = 0

        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="collector",
            level="info",
            event="collection_completed",
            detail=f"agents={summary['agents']} tokens={summary['tokens']} pot={summary['pot']} alerts={summary.get('alerts', 0)}",
            trace_id=trace_id,
            created_at=utc_now_iso(),
        ))

    except Exception as exc:
        logger.exception("collection failed")
        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="collector",
            level="error",
            event="collection_failed",
            detail=str(exc),
            trace_id=trace_id,
            created_at=utc_now_iso(),
        ))

    return summary


class PollingController:
    """定时采集控制器 — 参考 SignalHub PollingController 模式"""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self._started = False
        self._scan_lock = asyncio.Lock()
        self.last_summary: dict[str, int] | None = None
        self.last_error: str | None = None
        self.last_started_at: str | None = None
        self.last_completed_at: str | None = None
        self.mode = "auto"

        if AsyncIOScheduler is not None:
            self.scheduler = AsyncIOScheduler(timezone="UTC")
            self.scheduler.add_job(
                self.scheduled_scan,
                "interval",
                seconds=settings.poll_interval_seconds,
                kwargs={},
                id="degenclaw-poll",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        else:
            self.scheduler = None

    def start(self) -> None:
        if self._started:
            return
        if self.scheduler:
            self.scheduler.start()
        self._started = True

    def shutdown(self) -> None:
        if not self._started:
            return
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
        self._started = False

    async def scheduled_scan(self) -> None:
        if self.mode != "auto":
            return
        await self.scan_once(trigger="auto")

    async def scan_once(self, *, trigger: str) -> dict[str, int]:
        async with self._scan_lock:
            self.last_started_at = utc_now_iso()
            self.last_error = None
            try:
                summary = await run_collection(self.database, self.settings)
                self.last_completed_at = utc_now_iso()
                self.last_summary = {**summary, "trigger": trigger}
                return self.last_summary
            except Exception as exc:
                self.last_completed_at = utc_now_iso()
                self.last_error = str(exc)
                logger.exception("polling scan failed trigger=%s", trigger)
                raise

    def get_status(self) -> dict:
        return {
            "mode": self.mode,
            "running": self.mode == "auto",
            "is_scanning": self._scan_lock.locked(),
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "last_started_at": self.last_started_at,
            "last_completed_at": self.last_completed_at,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
        }

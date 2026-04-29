from __future__ import annotations

import asyncio
import logging

from config.settings import Settings
from db.database import Database
from db.models import (
    Agent, AgentSnapshot, LeaderboardSnapshot, SystemEvent, Token,
    build_event_id, utc_now_iso,
)
from collectors.degenclaw_collector import DegenClawCollector, MarketCollector, AIPotCollector
from collectors.season_manager import SeasonManager
from notifiers.feishu_notifier import FeishuNotifier
from parsers.degenclaw_parser import DegenClawParser
from scoring.engine import DegenClawScoreEngine
from signals.signal_engine import SignalEngine
from decision.event_window import EventWindowManager
from decision.engine import TradingDecisionEngine, DecisionInput
from decision.paper_trader import PaperTrader, PaperPosition

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

        # 1a. 赛季过滤：只保留当前赛季的 Agent
        season_mgr = SeasonManager()
        current_season = await season_mgr.fetch_current_season()
        if current_season:
            before = len(agents)
            filtered: list[Agent] = []
            filtered_snaps: list[AgentSnapshot] = []
            for agent, snap in zip(agents, snapshots):
                if snap.last_trade_at and not current_season.contains(snap.last_trade_at):
                    continue
                filtered.append(agent)
                filtered_snaps.append(snap)
            agents, snapshots = filtered, filtered_snaps
            removed = before - len(agents)
            if removed:
                logger.info("赛季过滤: 移除 %d 个非当季 Agent (剩 %d)", removed, len(agents))
        else:
            logger.info("未获取到赛季信息，不过滤")

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
            if current_season:
                score_results = score_engine.run_round(
                    season_start=current_season.start_date,
                    season_end=current_season.end_date,
                )
            else:
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


async def run_signal_generation(database: Database, settings: Settings) -> dict[str, int]:
    """执行一轮信号生成 + Paper Trading"""
    import json
    trace_id = build_event_id()
    now = utc_now_iso()
    summary: dict[str, int] = {"signals": 0, "buys": 0, "sells": 0}

    try:
        # 1. 获取最新评分，去重后取前十名 Agent
        all_scores = database.list_agent_scores(limit=200)
        if not all_scores:
            logger.info("signal generation skipped: no scores")
            return summary
        # 按 agent_id 去重保留最新一条，按总分排序取前十
        seen: dict[str, dict] = {}
        for s in all_scores:
            aid = s["agent_id"]
            if aid not in seen or s["scored_at"] > seen[aid]["scored_at"]:
                seen[aid] = s
        scores = sorted(seen.values(), key=lambda x: x["score_total"], reverse=True)[:10]

        # 2. 获取事件窗口
        window_mgr = EventWindowManager()
        window = window_mgr.get_current_window()

        # 3. 初始化决策引擎和 paper trader
        engine = TradingDecisionEngine(window_mgr)
        paper_trader = PaperTrader()

        # 加载已有的 open positions
        existing_positions = database.get_open_paper_positions()
        loaded = []
        for p in existing_positions:
            try:
                loaded.append(PaperPosition.from_record(p))
            except Exception:
                continue
        paper_trader.load_positions(loaded)

        # 4. 对前十名 Agent 逐一生成信号
        for score in scores:
            agent_id = score["agent_id"]
            agent = database.get_agent(agent_id)
            if not agent:
                continue

            snapshots = database.get_agent_snapshots(agent_id, limit=3)
            market = None
            if agent.get("token_address"):
                market = database.get_latest_market_snapshot(agent["token_address"])

            latest_snap = snapshots[0] if snapshots else {}
            rank_prev = snapshots[1].get("rank", 0) if len(snapshots) >= 2 else latest_snap.get("rank", 0)
            rank_oldest = snapshots[-1].get("rank", 0) if len(snapshots) >= 2 else latest_snap.get("rank", 0)

            rank_change_1h = rank_prev - (latest_snap.get("rank", 0) or 0)
            rank_change_24h = rank_oldest - (latest_snap.get("rank", 0) or 0)

            # 检查是否有持仓
            token_positions = [p for p in paper_trader.get_open_positions() if p.agent_id == agent_id]
            has_position = len(token_positions) > 0
            pos_pnl = token_positions[0].unrealized_pnl if token_positions else 0.0

            inp = DecisionInput(
                agent_id=agent_id,
                agent_name=agent.get("name", ""),
                token_address=agent.get("token_address", ""),
                score_total=score["score_total"],
                council_score=score["council_probability_score"],
                trading_score=score["trading_performance_score"],
                rank_trend_score=score["rank_trend_score"],
                token_market_score=score["token_market_score"],
                risk_penalty=score["risk_penalty"],
                rank=latest_snap.get("rank", 0) or 0,
                rank_change_1h=rank_change_1h,
                rank_change_24h=rank_change_24h,
                is_top_10=bool(latest_snap.get("is_top_10", False)),
                is_selected=bool(latest_snap.get("is_selected", False)),
                price_usd=float(market.get("price_usd", 0)) if market else 0,
                liquidity_usd=float(market.get("liquidity_usd", 0)) if market else 0,
                volume_24h=float(market.get("volume_24h", 0)) if market else 0,
                price_change_24h=float(market.get("price_change_24h", 0)) if market else 0,
                buy_slippage=float(market.get("buy_slippage", 0)) if market else 0,
                has_position=has_position,
                position_pnl_pct=pos_pnl,
            )

            signal = engine.decide(inp, window)
            if signal.action == "watch":
                continue

            # 保存信号
            from db.models import TradeSignalModel
            database.insert_trade_signal(TradeSignalModel(
                signal_id=signal.signal_id,
                agent_id=signal.agent_id,
                token_address=signal.token_address,
                agent_name=agent.get("name", ""),
                action=signal.action,
                confidence=signal.confidence,
                reason=signal.reason,
                key_factors=json.dumps(signal.key_factors),
                max_position_usdc=signal.max_position_usdc,
                slippage_limit_pct=signal.slippage_limit_pct,
                stop_loss_pct=signal.stop_loss_pct,
                take_profit_pct=signal.take_profit_pct,
                time_exit_hours=signal.time_exit_hours,
                risk_checks=json.dumps(signal.risk_checks),
                window=signal.window,
                status=signal.status,
                created_at=signal.created_at,
                expires_at=signal.expires_at,
            ))
            summary["signals"] += 1

            # 5. 执行 paper trade
            if signal.action in ("probe_buy", "confirm_buy"):
                pos = paper_trader.execute_buy(
                    signal_id=signal.signal_id,
                    agent_id=signal.agent_id,
                    token_address=signal.token_address,
                    action=signal.action,
                    max_position_usdc=signal.max_position_usdc,
                    price_usd=inp.price_usd,
                    liquidity_usd=inp.liquidity_usd,
                    buy_slippage=inp.buy_slippage,
                    stop_loss_pct=signal.stop_loss_pct,
                    take_profit_pct=signal.take_profit_pct,
                    time_exit_hours=signal.time_exit_hours,
                )
                if pos:
                    from db.models import PaperPositionModel
                    database.insert_paper_position(PaperPositionModel(
                        position_id=pos.position_id,
                        signal_id=pos.signal_id,
                        agent_id=pos.agent_id,
                        token_address=pos.token_address,
                        action=pos.action,
                        entry_price=pos.entry_price,
                        amount_token=pos.amount_token,
                        cost_usdc=pos.cost_usdc,
                        entry_slippage=pos.entry_slippage,
                        entered_at=pos.entered_at,
                        current_price=pos.current_price,
                        unrealized_pnl=pos.unrealized_pnl,
                        exit_price=pos.exit_price or 0,
                        realized_pnl=pos.realized_pnl or 0,
                        exit_slippage=pos.exit_slippage or 0,
                        exited_at=pos.exited_at or "",
                        exit_reason=pos.exit_reason or "",
                        stop_loss_pct=pos.stop_loss_pct,
                        take_profit_pct=pos.take_profit_pct,
                        time_exit_hours=pos.time_exit_hours,
                        status=pos.status,
                    ))
                    summary["buys"] += 1

        # 6. 更新持仓价格并检查退出
        for pos in paper_trader.get_open_positions():
            market = None
            if pos.token_address:
                market = database.get_latest_market_snapshot(pos.token_address)
            current_price = float(market.get("price_usd", 0)) if market else 0
            if current_price <= 0:
                continue

            paper_trader.update_price(pos, current_price)
            exit_reason = paper_trader.check_exit_conditions(pos, current_price)
            if exit_reason:
                sell_slippage = float(market.get("sell_slippage", 0)) if market else 0
                paper_trader.execute_sell(pos, current_price, pos.cost_usdc, sell_slippage, exit_reason)
                summary["sells"] += 1

            # 持久化持仓
            from db.models import PaperPositionModel
            database.update_paper_position(PaperPositionModel(
                position_id=pos.position_id,
                signal_id=pos.signal_id,
                agent_id=pos.agent_id,
                token_address=pos.token_address,
                action=pos.action,
                entry_price=pos.entry_price,
                amount_token=pos.amount_token,
                cost_usdc=pos.cost_usdc,
                entry_slippage=pos.entry_slippage,
                entered_at=pos.entered_at,
                current_price=pos.current_price,
                unrealized_pnl=pos.unrealized_pnl,
                exit_price=pos.exit_price or 0,
                realized_pnl=pos.realized_pnl or 0,
                exit_slippage=pos.exit_slippage or 0,
                exited_at=pos.exited_at or "",
                exit_reason=pos.exit_reason or "",
                stop_loss_pct=pos.stop_loss_pct,
                take_profit_pct=pos.take_profit_pct,
                time_exit_hours=pos.time_exit_hours,
                status=pos.status,
            ))

        logger.info("signal generation: %d signals, %d buys, %d sells",
                     summary["signals"], summary["buys"], summary["sells"])

        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="signal",
            level="info",
            event="signal_generation_completed",
            detail=f"signals={summary['signals']} buys={summary['buys']} sells={summary['sells']}",
            trace_id=trace_id,
            created_at=utc_now_iso(),
        ))

    except Exception as exc:
        logger.exception("signal generation failed")
        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="signal",
            level="error",
            event="signal_generation_failed",
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
        self._signal_lock = asyncio.Lock()
        self.last_summary: dict[str, int] | None = None
        self.last_error: str | None = None
        self.last_started_at: str | None = None
        self.last_completed_at: str | None = None
        self.last_signal_summary: dict[str, int] | None = None
        self.last_signal_error: str | None = None
        self.last_signal_started_at: str | None = None
        self.last_signal_completed_at: str | None = None
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
            self.scheduler.add_job(
                self.scheduled_signal_gen,
                "interval",
                seconds=900,  # 15 分钟
                kwargs={},
                id="degenclaw-signal",
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

    async def scheduled_signal_gen(self) -> None:
        if self.mode != "auto":
            return
        await self.signal_gen_once(trigger="auto")

    async def signal_gen_once(self, *, trigger: str) -> dict[str, int]:
        async with self._signal_lock:
            self.last_signal_started_at = utc_now_iso()
            self.last_signal_error = None
            try:
                summary = await run_signal_generation(self.database, self.settings)
                self.last_signal_completed_at = utc_now_iso()
                self.last_signal_summary = {**summary, "trigger": trigger}
                return self.last_signal_summary
            except Exception as exc:
                self.last_signal_completed_at = utc_now_iso()
                self.last_signal_error = str(exc)
                logger.exception("signal gen failed trigger=%s", trigger)
                raise

    def get_status(self) -> dict:
        return {
            "mode": self.mode,
            "running": self.mode == "auto",
            "is_scanning": self._scan_lock.locked(),
            "is_generating_signals": self._signal_lock.locked(),
            "poll_interval_seconds": self.settings.poll_interval_seconds,
            "signal_interval_seconds": 900,
            "last_started_at": self.last_started_at,
            "last_completed_at": self.last_completed_at,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
            "signal": {
                "last_started_at": self.last_signal_started_at,
                "last_completed_at": self.last_signal_completed_at,
                "last_error": self.last_signal_error,
                "last_summary": self.last_signal_summary,
            },
        }

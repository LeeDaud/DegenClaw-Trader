from __future__ import annotations

import asyncio
import logging
import time

from config.settings import Settings
from db.database import Database
from db.models import (
    Agent, AgentSnapshot, LeaderboardSnapshot, SystemEvent, Token,
    build_event_id, utc_now_iso,
)
from collectors.degenclaw_collector import DegenClawCollector, MarketCollector, AIPotCollector
from collectors.price_ticker import PriceTicker
from collectors.season_manager import SeasonManager
from notifiers.feishu_notifier import FeishuNotifier
from parsers.degenclaw_parser import DegenClawParser
from scoring.engine import DegenClawScoreEngine
from calibration.outcome_tracker import OutcomeTracker
from calibration.agent_volatility import AgentVolatilityTracker
from signals.signal_engine import SignalEngine
from signals.signal_state import SignalStateManager
from signals.candle_analyzer import CandleAnalyzer
from decision.event_window import EventWindowManager
from decision.engine import TradingDecisionEngine, DecisionInput
from decision.paper_trader import PaperTrader, PaperPosition

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except ModuleNotFoundError:
    AsyncIOScheduler = None  # fallback handled below

logger = logging.getLogger(__name__)

# Pot PnL 通知冷却：同一 sub_pot 15 分钟内不重复推送（次要防线，主防线在 SignalStateManager）
_pot_pnl_cooldown: dict[str, float] = {}
_POT_PNL_COOLDOWN_SECONDS = 900

# 信号状态管理器（跨采集周期持久化，方向确认计数需要跨周期累积）
_state_manager: SignalStateManager | None = None

# 高频价格采集器 + 烛图分析器（独立于主采集周期）
_price_ticker: PriceTicker | None = None
_candle_analyzer: CandleAnalyzer | None = None


def _get_state_manager() -> SignalStateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = SignalStateManager()
    return _state_manager


def _get_price_ticker(settings: Settings) -> PriceTicker:
    global _price_ticker
    if _price_ticker is None:
        _price_ticker = PriceTicker(settings)
    return _price_ticker


def _get_candle_analyzer(database: Database) -> CandleAnalyzer:
    global _candle_analyzer
    if _candle_analyzer is None:
        _candle_analyzer = CandleAnalyzer(database)
    return _candle_analyzer


async def run_collection(database: Database, settings: Settings,
                         price_ticker: PriceTicker | None = None) -> dict[str, int]:
    """执行一轮完整采集"""
    parser = DegenClawParser()
    degenclaw = DegenClawCollector(settings)
    market = MarketCollector(settings)
    pot = AIPotCollector(settings)
    trace_id = build_event_id()
    now = utc_now_iso()

    summary = {"agents": 0, "tokens": 0, "pot": 0}

    # 信号状态管理器（跨周期持久化，方向确认需累加之前轮次的读数）
    state_manager = _get_state_manager()

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
                # 过滤后重新分配排名 (去掉空缺)
                for i, snap in enumerate(filtered_snaps, start=1):
                    snap.rank = i
                    snap.is_top_10 = i <= 10
                logger.info("赛季过滤: 移除 %d 个非当季 Agent (剩 %d)，排名已重分配", removed, len(agents))
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
        # 更新高频价格采集器的地址缓存
        if price_ticker and token_addresses:
            price_ticker.update_address_cache(token_addresses)
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
            from db.models import (
                AIPotRound, CouncilAgentScore, CouncilEvaluation,
                CouncilLeaderboardScore, PotPnlSnapshot, PotSubAgent,
            )
            from monitoring.pot_monitor import PotPnlMonitor

            database.upsert_ai_pot_round(AIPotRound(
                round_id=pot_status["round_id"],
                round_start=pot_status["round_start"],
                round_end=pot_status["round_end"],
                status=pot_status["status"],
                selected_agents=pot_status.get("selected_agents", "[]"),
                pot_pnl=float(pot_status.get("pot_pnl", 0)),
                created_at=now,
                updated_at=now,
                season_id=pot_status.get("season_id", ""),
                season_name=pot_status.get("season_name", ""),
                total_capital=float(pot_status.get("total_capital", 0)),
                total_current_value=float(pot_status.get("total_current_value", 0)),
                total_realized_pnl=float(pot_status.get("total_realized_pnl", 0)),
                total_unrealized_pnl=float(pot_status.get("total_unrealized_pnl", 0)),
                return_pct=float(pot_status.get("return_pct", 0)),
                raw_data=pot_status.get("raw_data", "{}"),
            ))
            summary["pot"] = 1

            # 3a. 存储子池 + PnL 快照
            sub_pots = pot_status.get("sub_pots", [])
            for sp in sub_pots:
                database.upsert_pot_sub_agent(PotSubAgent(
                    round_id=pot_status["round_id"],
                    sub_pot_id=sp["sub_pot_id"],
                    name=sp["name"],
                    status=sp["status"],
                    agent_id=sp["agent_id"],
                    agent_name=sp["agent_name"],
                    token_address=sp["token_address"],
                    token_symbol=sp["token_symbol"],
                    starting_capital=sp["starting_capital"],
                    current_value=sp["current_value"],
                    realized_pnl=sp["realized_pnl"],
                    unrealized_pnl=sp["unrealized_pnl"],
                    final_pnl=sp["final_pnl"],
                    positions=sp.get("positions", "[]"),
                    snapshot_at=now,
                ))
                database.insert_pot_pnl_snapshot(PotPnlSnapshot(
                    sub_pot_id=sp["sub_pot_id"],
                    round_id=pot_status["round_id"],
                    current_value=sp["current_value"],
                    realized_pnl=sp["realized_pnl"],
                    unrealized_pnl=sp["unrealized_pnl"],
                    final_pnl=sp["final_pnl"],
                    snapshot_at=now,
                ))
            summary["sub_pots"] = len(sub_pots)

            # 3b. 存储评委会数据
            council_data = pot_status.get("council_data")
            if council_data and council_data.get("finalTop10"):
                eval_id = database.upsert_council_evaluation(CouncilEvaluation(
                    season_id=pot_status.get("season_id", ""),
                    season_name=pot_status.get("season_name", ""),
                    pot_size=float(council_data.get("potSize", 0) or 0),
                    total_agents_analyzed=int(council_data.get("totalAgentsAnalyzed", 0)),
                    consensus_agents=json.dumps(council_data.get("consensusAgents", []), ensure_ascii=False),
                    model_verdicts=json.dumps(council_data.get("modelVerdicts", {}), ensure_ascii=False),
                    raw_data=json.dumps(council_data, ensure_ascii=False),
                    fetched_at=now,
                ))

                # 写入各 agent 评分
                agent_scores = []
                for i, agent_entry in enumerate(council_data.get("finalTop10", []), start=1):
                    agent_name = agent_entry.get("agentName", agent_entry.get("name", ""))
                    if not agent_name:
                        continue
                    per_model = agent_entry.get("perModelRationale", agent_entry.get("perModelReason", {}))
                    agent_scores.append(CouncilAgentScore(
                        season_id=pot_status.get("season_id", ""),
                        evaluation_id=eval_id,
                        agent_name=agent_name,
                        rank=i,
                        votes=int(agent_entry.get("votes", 0)),
                        per_model_rationale=json.dumps(per_model, ensure_ascii=False),
                        created_at=now,
                    ))
                if agent_scores:
                    database.insert_council_agent_scores(agent_scores)

                # 3c. 尝试按名称匹配本地 Agent，写入 leaderboard score
                for score in agent_scores:
                    agent_row = database.get_agent_by_name(score.agent_name)
                    if agent_row:
                        database.upsert_council_leaderboard_score(CouncilLeaderboardScore(
                            agent_id=agent_row["agent_id"],
                            season_id=pot_status.get("season_id", ""),
                            council_rank=score.rank,
                            council_score=float(score.votes),
                            council_votes=score.votes,
                            fetched_at=now,
                        ))

            # 3d. PnL 监控 — 对比快照 → 飞书通知
            if settings.pot_monitor_enabled and sub_pots and settings.feishu_alerts_enabled:
                monitor = PotPnlMonitor(database, state_manager)
                changes = monitor.check_sub_pot_changes(
                    round_id=pot_status["round_id"],
                    sub_pots=sub_pots,
                    settings=settings,
                )
                if changes:
                    notifier = FeishuNotifier(settings.feishu_webhook_url)
                    if notifier.is_configured():
                        now = time.time()
                        sent = 0
                        skipped_tier = 0
                        skipped_cooldown = 0
                        skipped_direction = 0
                        for c in changes:
                            # 仅推送 warning+ 级别
                            if c.get("tier", "info") == "info":
                                skipped_tier += 1
                                continue
                            # 方向冷却检查（通过 StateManager）
                            spid = c["sub_pot_id"]
                            raw_dir = c.get("direction", "stable")
                            bullbear: str | None = None
                            if raw_dir in ("up", "steep_up", "recovery_up"):
                                bullbear = "bullish"
                            elif raw_dir in ("down", "steep_down", "pullback_down"):
                                bullbear = "bearish"
                            if bullbear is not None and not state_manager.can_notify(spid, bullbear):
                                skipped_direction += 1
                                continue
                            # 同一 sub_pot 冷却期内不重复（次要防线）
                            last = _pot_pnl_cooldown.get(spid, 0)
                            if now - last < _POT_PNL_COOLDOWN_SECONDS:
                                skipped_cooldown += 1
                                continue
                            _pot_pnl_cooldown[spid] = now
                            if bullbear is not None:
                                state_manager.mark_notified(spid, bullbear)
                            card = PotPnlMonitor.build_feishu_card(c)
                            notifier.send_card(card, title=f"Pot PnL {c['name']}")
                            sent += 1
                        if sent:
                            logger.info("Pot PnL 监控: %d 条推送 (info跳过=%d, 冷却跳过=%d, 方向冷却=%d)",
                                        sent, skipped_tier, skipped_cooldown, skipped_direction)

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
        outcome_tracker = OutcomeTracker(database, state_manager)
        try:
            db_config = {}
            raw_config = database.get_all_config()
            for k, v in raw_config.items():
                try:
                    db_config[k] = float(v) if "." in v else int(v)
                except (ValueError, TypeError):
                    db_config[k] = v
        except Exception:
            db_config = {}
            logger.warning("加载信号配置失败，使用默认值", exc_info=True)

        volatility_tracker = AgentVolatilityTracker(database)
        volatility_tracker.refresh()
        signal_engine = SignalEngine(database, state_manager, thresholds=db_config,
                                     outcome_tracker=outcome_tracker,
                                     volatility_tracker=volatility_tracker)
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

            # win_rate 趋势：跨多快照计算
            latest_wr = float(latest_snap.get("win_rate", 0) or 0)
            if len(snapshots) >= 3:
                old_wr = float(snapshots[-1].get("win_rate", 0) or 0)
                win_rate_change = latest_wr - old_wr
            elif len(snapshots) >= 2:
                prev_wr = float(snapshots[1].get("win_rate", 0) or 0)
                win_rate_change = latest_wr - prev_wr
            else:
                win_rate_change = 0.0

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
                win_rate=latest_wr,
                win_rate_change=win_rate_change,
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


async def run_price_tick(database: Database, settings: Settings) -> dict[str, int]:
    """执行一轮高频价格采集 + 烛图反转分析"""
    if not settings.price_tick_enabled:
        return {"ticks": 0, "alerts": 0}

    ticker = _get_price_ticker(settings)
    analyzer = _get_candle_analyzer(database)
    now = utc_now_iso()
    summary = {"ticks": 0, "alerts": 0}

    try:
        ticks = await ticker.tick()
        if ticks:
            database.insert_price_ticks(ticks)
            summary["ticks"] = len(ticks)

            # 烛图反转分析
            alerts = analyzer.run_check()
            if alerts:
                summary["alerts"] = len(alerts)

                # 飞书通知
                if settings.feishu_alerts_enabled:
                    notifier = FeishuNotifier(settings.feishu_webhook_url)
                    if notifier.is_configured():
                        alert_dicts = [a.as_record() for a in alerts]
                        sent = notifier.send_alerts_batch(alert_dicts)
                        if sent > 0:
                            for alert in alerts:
                                database.mark_alert_notified(alert.alert_id)
                        logger.info("烛图反转: %d 条预警, 飞书推送 %d", len(alerts), sent)

        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="price_tick",
            level="info",
            event="price_tick_completed",
            detail=f"ticks={summary['ticks']} alerts={summary['alerts']}",
            trace_id=build_event_id(),
            created_at=now,
        ))

    except Exception as exc:
        logger.exception("price tick failed: %s", exc)
        database.insert_system_event(SystemEvent(
            event_id=build_event_id(),
            module="price_tick",
            level="error",
            event="price_tick_failed",
            detail=str(exc),
            trace_id=build_event_id(),
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
        self._price_tick_lock = asyncio.Lock()
        self.last_summary: dict[str, int] | None = None
        self.last_error: str | None = None
        self.last_started_at: str | None = None
        self.last_completed_at: str | None = None
        self.last_signal_summary: dict[str, int] | None = None
        self.last_signal_error: str | None = None
        self.last_signal_started_at: str | None = None
        self.last_signal_completed_at: str | None = None
        # 校准任务状态追踪
        self.last_outcome_check_at: str | None = None
        self.last_outcome_check_stats: dict | None = None
        self.last_auto_tune_at: str | None = None
        self.last_auto_tune_adjustments: list[str] | None = None
        self.last_full_calibration_at: str | None = None
        self.last_full_calibration_f1_old: float | None = None
        self.last_full_calibration_f1_new: float | None = None
        # 高频价格 tick 状态追踪
        self.last_price_tick_at: str | None = None
        self.last_price_tick_summary: dict[str, int] | None = None
        self.last_price_tick_error: str | None = None
        self.mode = "auto"

        if AsyncIOScheduler is not None:
            from datetime import datetime, timedelta, timezone
            # 延迟首次触发，避免与 startup scan 竞态
            first_run = datetime.now(timezone.utc) + timedelta(seconds=settings.poll_interval_seconds)
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
                next_run_time=first_run,
            )
            self.scheduler.add_job(
                self.scheduled_signal_gen,
                "interval",
                seconds=900,
                kwargs={},
                id="degenclaw-signal",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=first_run + timedelta(seconds=900),
            )
            # 结果回检（每 15 分钟）
            self.scheduler.add_job(
                self.scheduled_outcome_check,
                "interval",
                seconds=900,
                kwargs={},
                id="degenclaw-outcome-check",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=first_run + timedelta(seconds=600),
            )
            # 自动调参（每天凌晨 3:00）
            self.scheduler.add_job(
                self.scheduled_auto_tune,
                "cron",
                hour=3,
                minute=0,
                kwargs={},
                id="degenclaw-auto-tune",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            # 全校准回测（每天凌晨 2:00，先于 auto_tune）
            self.scheduler.add_job(
                self.scheduled_full_calibration,
                "cron",
                hour=2,
                minute=0,
                kwargs={},
                id="degenclaw-full-calibration",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            # 高频价格采集 + 烛图反转分析（独立周期）
            if settings.price_tick_enabled:
                # 首次运行 = 主采集首次 + 一半tick间隔（错峰减少DB锁争用）
                tick_first = first_run + timedelta(seconds=settings.price_tick_interval_seconds // 2)
                self.scheduler.add_job(
                    self.scheduled_price_tick,
                    "interval",
                    seconds=settings.price_tick_interval_seconds,
                    kwargs={},
                    id="degenclaw-price-tick",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    next_run_time=tick_first,
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
                ticker = _get_price_ticker(self.settings) if self.settings.price_tick_enabled else None
                summary = await run_collection(self.database, self.settings, price_ticker=ticker)
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

    async def scheduled_price_tick(self) -> None:
        if self.mode != "auto":
            return
        await self.price_tick_once(trigger="auto")

    async def price_tick_once(self, *, trigger: str) -> dict[str, int]:
        async with self._price_tick_lock:
            self.last_price_tick_at = utc_now_iso()
            self.last_price_tick_error = None
            try:
                summary = await run_price_tick(self.database, self.settings)
                self.last_price_tick_summary = {**summary, "trigger": trigger}
                return self.last_price_tick_summary
            except Exception as exc:
                self.last_price_tick_error = str(exc)
                logger.exception("price tick failed trigger=%s", trigger)
                raise

    async def scheduled_outcome_check(self) -> None:
        if self.mode != "auto":
            return
        try:
            db = Database(self.settings.db_path)
            state_mgr = SignalStateManager()
            tracker = OutcomeTracker(db, state_mgr)
            stats = tracker.check_outcomes()
            self.last_outcome_check_at = utc_now_iso()
            self.last_outcome_check_stats = stats
            logger.info("Outcome check: checked=%d correct=%d wrong=%d skipped=%d",
                        stats["checked"], stats["correct"], stats["wrong"], stats["skipped"])
        except Exception as exc:
            logger.warning("Outcome check failed: %s", exc)

    async def scheduled_auto_tune(self) -> None:
        if self.mode != "auto":
            return
        try:
            db = Database(self.settings.db_path)
            state_mgr = SignalStateManager()
            tracker = OutcomeTracker(db, state_mgr)
            result = tracker.auto_tune()
            self.last_auto_tune_at = utc_now_iso()
            self.last_auto_tune_adjustments = result.get("adjusted_keys")
            if result["adjusted_keys"]:
                logger.info("Auto tune: adjusted %s", result["adjusted_keys"])
        except Exception as exc:
            logger.warning("Auto tune failed: %s", exc)

    async def scheduled_full_calibration(self) -> None:
        if self.mode != "auto":
            return
        try:
            db = Database(self.settings.db_path)
            from calibration.auto_calibrator import AutoCalibrator
            calibrator = AutoCalibrator(db)
            result = calibrator.quick_calibrate()
            self.last_full_calibration_at = utc_now_iso()
            if result.get("success"):
                self.last_full_calibration_f1_old = result.get("old_f1")
                self.last_full_calibration_f1_new = result.get("new_f1")
                logger.info("Calibration: F1 %.3f → %.3f",
                            result.get("old_f1", 0), result.get("new_f1", 0))
            else:
                logger.info("Calibration skipped: %s", result.get("reason", "unknown"))
        except Exception as exc:
            logger.warning("Calibration failed: %s", exc)

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
            "price_tick": {
                "is_running": self._price_tick_lock.locked(),
                "interval_seconds": self.settings.price_tick_interval_seconds,
                "enabled": self.settings.price_tick_enabled,
                "last_run_at": self.last_price_tick_at,
                "last_error": self.last_price_tick_error,
                "last_summary": self.last_price_tick_summary,
            },
            "calibration": {
                "outcome_check": {
                    "last_run_at": self.last_outcome_check_at,
                    "stats": self.last_outcome_check_stats,
                },
                "auto_tune": {
                    "last_run_at": self.last_auto_tune_at,
                    "last_adjustments": self.last_auto_tune_adjustments,
                },
                "full_calibration": {
                    "last_run_at": self.last_full_calibration_at,
                    "f1_old": self.last_full_calibration_f1_old,
                    "f1_new": self.last_full_calibration_f1_new,
                },
            },
        }

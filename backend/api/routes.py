from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from collectors.season_manager import SeasonManager
from db.database import Database
from db.models import utc_now_iso
from notifiers.feishu_notifier import FeishuNotifier
from scheduler.scheduler import PollingController
from scoring.engine import DegenClawScoreEngine
from signals.signal_engine import SignalEngine

router = APIRouter()


def get_database(request: Request) -> Database:
    return request.app.state.database


def get_controller(request: Request) -> PollingController:
    return request.app.state.polling_controller


def _api_ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "timestamp": utc_now_iso()}


def _api_error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}, "timestamp": utc_now_iso()}


# --- 健康检查 ---

@router.get("/health")
async def healthcheck() -> dict[str, Any]:
    return _api_ok({"status": "ok", "app": "degenclaw-alpha-engine"})


# --- Agent ---

@router.get("/agents")
async def list_agents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    database = get_database(request)
    season_mgr = SeasonManager()
    current_season = await season_mgr.fetch_current_season()
    if current_season:
        agents = database.list_agents(limit=limit, offset=offset,
                                      season_start=current_season.start_date,
                                      season_end=current_season.end_date)
        total = database.count_agents(season_start=current_season.start_date,
                                      season_end=current_season.end_date)
    else:
        agents = database.list_agents(limit=limit, offset=offset)
        total = database.count_agents()
    enriched = []
    for agent in agents:
        snapshot = database.get_agent_latest_snapshot(agent["agent_id"])
        market = None
        if agent["token_address"]:
            market = database.get_latest_market_snapshot(agent["token_address"])
        latest_score = database.get_agent_score_history(agent["agent_id"], limit=1)
        enriched.append({
            **agent,
            "latest_snapshot": snapshot,
            "latest_market": market,
            "latest_score": latest_score[0] if latest_score else None,
        })
    return _api_ok({"agents": enriched, "total": total})


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, request: Request) -> dict[str, Any]:
    database = get_database(request)
    agent = database.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    snapshots = database.get_agent_snapshots(agent_id, limit=100)
    market = None
    if agent["token_address"]:
        market_data = database.get_latest_market_snapshot(agent["token_address"])
        market_history = database.get_token_market_snapshots(agent["token_address"], limit=100)
        market = {"latest": market_data, "history": market_history}
    scores = database.get_agent_score_history(agent_id, limit=50)
    return _api_ok({
        **agent,
        "snapshots": snapshots,
        "market": market,
        "scores": scores,
    })


@router.get("/agents/{agent_id}/snapshots")
async def get_agent_snapshots(
    agent_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    database = get_database(request)
    snapshots = database.get_agent_snapshots(agent_id, limit=limit)
    return _api_ok({"agent_id": agent_id, "snapshots": snapshots})


# --- Token ---

@router.get("/tokens")
async def list_tokens(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    database = get_database(request)
    tokens = database.list_tokens(limit=limit, offset=offset)
    enriched = []
    for token in tokens:
        market = database.get_latest_market_snapshot(token["token_address"])
        enriched.append({**token, "latest_market": market})
    return _api_ok({"tokens": enriched})


@router.get("/tokens/{token_address}")
async def get_token(token_address: str, request: Request) -> dict[str, Any]:
    database = get_database(request)
    token = database.get_token(token_address)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    market = database.get_latest_market_snapshot(token_address)
    history = database.get_token_market_snapshots(token_address, limit=100)
    return _api_ok({**token, "latest_market": market, "history": history})


@router.get("/tokens/{token_address}/snapshots")
async def get_token_snapshots(
    token_address: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    database = get_database(request)
    snapshots = database.get_token_market_snapshots(token_address, limit=limit)
    return _api_ok({"token_address": token_address, "snapshots": snapshots})


# --- Dashboard ---

@router.get("/dashboard")
async def get_dashboard(request: Request) -> dict[str, Any]:
    database = get_database(request)
    controller = get_controller(request)
    summary = database.get_dashboard_summary()
    return _api_ok({
        **summary,
        "polling_status": controller.get_status(),
    })


# --- Events ---

@router.get("/events")
async def list_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    module: str | None = Query(default=None),
    level: str | None = Query(default=None),
) -> dict[str, Any]:
    database = get_database(request)
    events = database.list_system_events(limit=limit, offset=offset, module=module, level=level)
    return _api_ok({"events": events})


# --- Alerts ---

@router.get("/alerts")
async def list_alerts(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    alert_type: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    unread_only: bool = Query(default=False),
) -> dict[str, Any]:
    database = get_database(request)
    alerts = database.list_alerts(limit=limit, offset=offset, alert_type=alert_type, agent_id=agent_id, unread_only=unread_only)
    unread_count = database.count_unread_alerts()
    return _api_ok({"alerts": alerts, "unread_count": unread_count})


@router.post("/alerts/scan")
async def trigger_signal_scan(request: Request) -> dict[str, Any]:
    """手动触发一轮信号扫描"""
    database = get_database(request)
    settings = request.app.state.settings
    engine = SignalEngine(database)
    alerts = engine.run_check()
    if alerts and settings.feishu_alerts_enabled:
        notifier = FeishuNotifier(settings.feishu_webhook_url)
        if notifier.is_configured():
            sent = notifier.send_alerts_batch([a.as_record() for a in alerts])
            for alert in alerts:
                database.mark_alert_notified(alert.alert_id)
            return _api_ok({"alerts": len(alerts), "notified": sent})
    return _api_ok({"alerts": len(alerts), "notified": 0})


@router.post("/alerts/{alert_id}/notified")
async def mark_alert_notified(alert_id: str, request: Request) -> dict[str, Any]:
    database = get_database(request)
    database.mark_alert_notified(alert_id)
    return _api_ok({"alert_id": alert_id, "notified": True})


# --- Scoring ---


@router.get("/scores")
async def list_scores(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    database = get_database(request)
    scores = database.list_agent_scores(limit=limit, offset=offset, agent_id=agent_id)
    return _api_ok({"scores": scores})


@router.get("/scores/{agent_id}")
async def get_agent_scores(
    agent_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    database = get_database(request)
    scores = database.get_agent_score_history(agent_id, limit=limit)
    return _api_ok({"agent_id": agent_id, "scores": scores})


@router.post("/scores/scan")
async def trigger_score_scan(request: Request) -> dict[str, Any]:
    """手动触发一轮评分"""
    database = get_database(request)
    season_mgr = SeasonManager()
    current_season = await season_mgr.fetch_current_season()
    if current_season:
        engine = DegenClawScoreEngine(database)
        results = engine.run_round(season_start=current_season.start_date,
                                   season_end=current_season.end_date)
    else:
        engine = DegenClawScoreEngine(database)
        results = engine.run_round()
    for score in results:
        database.insert_agent_score(score)
    return _api_ok({"scored": len(results)})


# --- Trade Signals ---


@router.get("/signals")
async def list_signals(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    database = get_database(request)
    signals = database.list_trade_signals(limit=limit, offset=offset, status=status)
    return _api_ok({"signals": signals})


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: str, request: Request) -> dict[str, Any]:
    database = get_database(request)
    signal = database.get_trade_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _api_ok(signal)


# --- Paper Positions ---


@router.get("/positions/paper")
async def list_paper_positions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
) -> dict[str, Any]:
    database = get_database(request)
    positions = database.list_paper_positions(limit=limit, offset=offset, status=status)
    return _api_ok({"positions": positions})


@router.get("/positions/paper/{position_id}")
async def get_paper_position(position_id: str, request: Request) -> dict[str, Any]:
    database = get_database(request)
    position = database.get_paper_position(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return _api_ok(position)


# --- Event Window ---


@router.get("/event-window")
async def get_event_window(request: Request) -> dict[str, Any]:
    from decision.event_window import EventWindowManager
    mgr = EventWindowManager()
    w = mgr.get_current_window()
    return _api_ok({
        "window": w.window,
        "risk_level": w.risk_level,
        "allowed_actions": w.allowed_actions,
        "position_multiplier": w.position_multiplier,
    })


# --- Paper Performance ---


@router.get("/performance/paper")
async def get_paper_performance(request: Request) -> dict[str, Any]:
    database = get_database(request)
    closed = database.list_paper_positions(limit=500, status="closed")
    open_positions = database.get_open_paper_positions()

    total_trades = len(closed)
    winning = [p for p in closed if p.get("realized_pnl", 0) > 0]
    losing = [p for p in closed if p.get("realized_pnl", 0) <= 0]
    win_rate = round(len(winning) / total_trades * 100, 1) if total_trades > 0 else 0
    total_pnl = sum(p.get("realized_pnl", 0) for p in closed)
    avg_pnl = round(total_pnl / total_trades, 2) if total_trades > 0 else 0
    best_trade = max(winning, key=lambda p: p.get("realized_pnl", 0)) if winning else None
    worst_trade = min(losing, key=lambda p: p.get("realized_pnl", 0)) if losing else None

    return _api_ok({
        "summary": {
            "total_trades": total_trades,
            "open_positions": len(open_positions),
            "win_rate": win_rate,
            "total_pnl_usdc": round(total_pnl, 2),
            "avg_pnl_usdc": avg_pnl,
            "best_trade": best_trade.get("realized_pnl", 0) if best_trade else 0,
            "worst_trade": worst_trade.get("realized_pnl", 0) if worst_trade else 0,
        },
        "recent_trades": closed[:20],
        "open_positions": open_positions,
    })


# --- Control ---

@router.get("/control/polling")
async def get_polling_status(request: Request) -> dict[str, Any]:
    controller = get_controller(request)
    return _api_ok(controller.get_status())


@router.post("/control/polling/scan")
async def trigger_scan(request: Request) -> dict[str, Any]:
    controller = get_controller(request)
    result = await controller.scan_once(trigger="manual")
    return _api_ok(result)


@router.post("/control/signals/generate")
async def trigger_signal_generation(request: Request) -> dict[str, Any]:
    controller = get_controller(request)
    result = await controller.signal_gen_once(trigger="manual")
    return _api_ok(result)

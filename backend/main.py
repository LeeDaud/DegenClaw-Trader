from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from config.settings import load_settings
from db.database import Database
from db.models import build_event_id, SystemEvent, utc_now_iso
from logger.logger import setup_logging
from scheduler.scheduler import PollingController

logger = logging.getLogger(__name__)


async def run_initial_collection(controller: PollingController) -> None:
    try:
        await controller.scan_once(trigger="startup")
    except Exception:
        logger.exception("initial collection failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    settings = load_settings()
    database = Database(settings.db_path)
    database.init_db()

    app.state.settings = settings
    app.state.database = database

    controller = PollingController(database, settings)
    app.state.polling_controller = controller
    controller.start()

    # 启动时采集一次
    asyncio.create_task(run_initial_collection(controller))

    # 记录启动事件
    database.insert_system_event(SystemEvent(
        event_id=build_event_id(),
        module="system",
        level="info",
        event="app_started",
        detail=f"source={settings.collector_source} interval={settings.poll_interval_seconds}s",
        trace_id="",
        created_at=utc_now_iso(),
    ))

    yield

    # 关闭
    database.insert_system_event(SystemEvent(
        event_id=build_event_id(),
        module="system",
        level="info",
        event="app_shutdown",
        detail="",
        trace_id="",
        created_at=utc_now_iso(),
    ))
    controller.shutdown()


def create_app() -> FastAPI:
    settings = load_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="DegenClaw Alpha Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api/v1")

    return app


app = create_app()

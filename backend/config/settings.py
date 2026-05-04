from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip()
        if not env_key or env_key in os.environ:
            continue
        env_value = value.strip()
        if len(env_value) >= 2 and env_value[0] == env_value[-1] and env_value[0] in {"'", '"'}:
            env_value = env_value[1:-1]
        os.environ[env_key] = env_value


_load_env_file(PROJECT_ROOT / ".env")
_load_env_file(PROJECT_ROOT / ".env.local")


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    db_path: Path
    host: str
    port: int
    cors_origins: list[str]
    collector_source: str
    degenclaw_endpoint: str | None
    virtuals_max_pages: int
    degenclaw_app_base_url: str
    dexscreener_endpoint: str | None
    poll_interval_seconds: int
    price_tick_enabled: bool
    price_tick_interval_seconds: int
    request_timeout_seconds: int
    log_level: str
    feishu_webhook_url: str | None
    feishu_alerts_enabled: bool
    pot_pnl_change_threshold: float
    pot_roi_change_threshold: float
    pot_monitor_enabled: bool
    # 4-tier thresholds
    pot_pnl_tier_info_pct: float
    pot_pnl_tier_warning_pct: float
    pot_pnl_tier_important_pct: float
    pot_pnl_tier_critical_pct: float
    pot_roi_tier_info_pct: float
    pot_roi_tier_warning_pct: float
    pot_roi_tier_important_pct: float
    pot_roi_tier_critical_pct: float


def load_settings() -> Settings:
    return Settings(
        app_name=os.getenv("DC_APP_NAME", "DegenClaw Alpha Engine"),
        db_path=Path(os.getenv("DC_DB_PATH", str(PROJECT_ROOT / ".." / "data" / "degenclaw.db"))),
        host=os.getenv("DC_HOST", "0.0.0.0"),
        port=int(os.getenv("DC_PORT", "8000")),
        cors_origins=[
            item.strip()
            for item in (os.getenv("DC_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","))
            if item.strip()
        ],
        collector_source=os.getenv("COLLECTOR_SOURCE", "mock"),
        degenclaw_endpoint=os.getenv("DEGENCLAW_ENDPOINT") or None,
        virtuals_max_pages=max(int(os.getenv("VIRTUALS_MAX_PAGES", "3")), 1),
        degenclaw_app_base_url=os.getenv("DEGENCLAW_APP_BASE_URL", "https://app.virtuals.io"),
        dexscreener_endpoint=os.getenv("DEXSCREENER_ENDPOINT") or None,
        poll_interval_seconds=max(int(os.getenv("POLL_INTERVAL_SECONDS", "60")), 5),
        price_tick_enabled=_to_bool(os.getenv("DC_PRICE_TICK_ENABLED"), True),
        price_tick_interval_seconds=max(int(os.getenv("DC_PRICE_TICK_INTERVAL_SECONDS", "15")), 5),
        request_timeout_seconds=max(int(os.getenv("REQUEST_TIMEOUT_SECONDS", "15")), 3),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL") or None,
        feishu_alerts_enabled=_to_bool(os.getenv("FEISHU_ALERTS_ENABLED"), False),
        pot_pnl_change_threshold=float(os.getenv("POT_PNL_CHANGE_THRESHOLD", "10.0")),
        pot_roi_change_threshold=float(os.getenv("POT_ROI_CHANGE_THRESHOLD", "5.0")),
        pot_monitor_enabled=_to_bool(os.getenv("POT_MONITOR_ENABLED"), True),
        pot_pnl_tier_info_pct=float(os.getenv("DC_POT_PNL_TIER_INFO_PCT", "3.0")),
        pot_pnl_tier_warning_pct=float(os.getenv("DC_POT_PNL_TIER_WARNING_PCT", "8.0")),
        pot_pnl_tier_important_pct=float(os.getenv("DC_POT_PNL_TIER_IMPORTANT_PCT", "15.0")),
        pot_pnl_tier_critical_pct=float(os.getenv("DC_POT_PNL_TIER_CRITICAL_PCT", "25.0")),
        pot_roi_tier_info_pct=float(os.getenv("DC_POT_ROI_TIER_INFO_PCT", "2.0")),
        pot_roi_tier_warning_pct=float(os.getenv("DC_POT_ROI_TIER_WARNING_PCT", "5.0")),
        pot_roi_tier_important_pct=float(os.getenv("DC_POT_ROI_TIER_IMPORTANT_PCT", "10.0")),
        pot_roi_tier_critical_pct=float(os.getenv("DC_POT_ROI_TIER_CRITICAL_PCT", "20.0")),
    )

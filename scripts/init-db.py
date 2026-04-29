#!/usr/bin/env python
"""初始化数据库和模拟数据"""
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from config.settings import load_settings
from db.database import Database
from db.models import (
    Agent, AgentSnapshot, Token, TokenMarketSnapshot,
    AIPotRound, LeaderboardSnapshot, SystemEvent, build_event_id, utc_now_iso,
)
from collectors.mock_data import get_mock_agents, MOCK_TOKENS


def _time_ago(minutes: int) -> str:
    """生成过去某个时间的 ISO 字符串"""
    dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


# 历史快照数据：每轮定义关键信号 Agent 的排名和收益变化
# agent_011 LambdaSurge: 15→13→11 持续上升
# agent_012 MuDump: 8→11→14 持续下跌
# agent_013 NuRocket: 25→20→16 排名飙升 + 收益暴涨
# agent_014 XiPlunge: 25→35→42 排名暴跌 + 收益暴跌
# agent_015 OmicronRise: 7→5→3 排名上升 + 收益改善

HISTORY_ROUNDS = [
    {  # T-60min: 基线
        "time_minutes": 60,
        "overrides": {
            "agent_011": {"rank": 15, "pnl_24h": 2.1, "pnl_7d": 12.5, "win_rate": 55.0, "max_drawdown": -12.0},
            "agent_012": {"rank": 8, "pnl_24h": 5.2, "pnl_7d": 22.0, "win_rate": 62.0, "max_drawdown": -8.0},
            "agent_013": {"rank": 25, "pnl_24h": 1.8, "pnl_7d": 8.5, "win_rate": 52.0, "max_drawdown": -15.0},
            "agent_014": {"rank": 25, "pnl_24h": -2.1, "pnl_7d": 5.0, "win_rate": 50.0, "max_drawdown": -12.0},
            "agent_015": {"rank": 7, "pnl_24h": 4.2, "pnl_7d": 25.0, "win_rate": 62.0, "max_drawdown": -10.0},
        },
    },
    {  # T-30min: 趋势中期
        "time_minutes": 30,
        "overrides": {
            "agent_011": {"rank": 13, "pnl_24h": 8.5, "pnl_7d": 28.0, "win_rate": 65.0, "max_drawdown": -8.0},
            "agent_012": {"rank": 11, "pnl_24h": -3.5, "pnl_7d": 10.0, "win_rate": 50.0, "max_drawdown": -15.0},
            "agent_013": {"rank": 20, "pnl_24h": 10.2, "pnl_7d": 35.0, "win_rate": 68.0, "max_drawdown": -6.0},
            "agent_014": {"rank": 35, "pnl_24h": -8.5, "pnl_7d": -12.0, "win_rate": 40.0, "max_drawdown": -25.0},
            "agent_015": {"rank": 5, "pnl_24h": 9.8, "pnl_7d": 35.0, "win_rate": 68.0, "max_drawdown": -7.0},
        },
    },
    {  # T-15min: 接近当前
        "time_minutes": 15,
        "overrides": {
            "agent_011": {"rank": 11, "pnl_24h": 15.2, "pnl_7d": 45.0, "win_rate": 72.0, "max_drawdown": -5.0},
            "agent_012": {"rank": 14, "pnl_24h": -8.5, "pnl_7d": -5.0, "win_rate": 42.0, "max_drawdown": -20.0},
            "agent_013": {"rank": 16, "pnl_24h": 18.5, "pnl_7d": 58.0, "win_rate": 78.0, "max_drawdown": -3.5},
            "agent_014": {"rank": 42, "pnl_24h": -15.0, "pnl_7d": -28.0, "win_rate": 32.0, "max_drawdown": -32.0},
            "agent_015": {"rank": 3, "pnl_24h": 12.8, "pnl_7d": 40.0, "win_rate": 72.0, "max_drawdown": -6.0},
        },
    },
]


def write_historical_snapshots(database: Database):
    """写入 3 轮历史快照让信号引擎有趋势可分析"""
    all_agents = get_mock_agents()
    agent_map = {a["id"]: a for a in all_agents}

    for round_data in HISTORY_ROUNDS:
        ts = _time_ago(round_data["time_minutes"])
        overrides = round_data["overrides"]
        snapshots = []

        for agent_id, override in overrides.items():
            base = agent_map.get(agent_id, {})
            snapshots.append(AgentSnapshot(
                agent_id=agent_id,
                rank=override.get("rank", base.get("rank", 0)),
                pnl_24h=override.get("pnl_24h", base.get("pnl_24h", 0)),
                pnl_7d=override.get("pnl_7d", base.get("pnl_7d", 0)),
                win_rate=override.get("win_rate", base.get("win_rate", 0)),
                max_drawdown=override.get("max_drawdown", base.get("max_drawdown", 0)),
                trade_count=base.get("trade_count", 0),
                is_top_10=override.get("rank", 99) <= 10,
                is_selected=False,
                snapshot_at=ts,
            ))

        database.insert_agent_snapshots(snapshots)
    print(f"写入 {len(HISTORY_ROUNDS) * 5} 条历史快照（{len(HISTORY_ROUNDS)} 轮 × 5 个信号 Agent）")


def main():
    settings = load_settings()
    database = Database(settings.db_path)
    database.init_db()
    print(f"数据库初始化完成: {settings.db_path}")

    now = utc_now_iso()

    # 写入模拟 Agent
    for item in get_mock_agents():
        agent = Agent(
            agent_id=item["id"],
            name=item["name"],
            profile_url=f"https://app.virtuals.io/agents/{item['id']}",
            token_address=item.get("token_address", ""),
            chain="base",
            created_at=now,
            updated_at=now,
        )
        database.upsert_agent(agent)

    print(f"写入 {len(get_mock_agents())} 个 Agent")

    # 写入历史快照（信号引擎需要至少 2 条快照做趋势分析）
    write_historical_snapshots(database)

    # 写入最新一轮快照
    snapshots = []
    for item in get_mock_agents():
        snapshots.append(AgentSnapshot(
            agent_id=item["id"],
            rank=item["rank"],
            pnl_24h=item["pnl_24h"],
            pnl_7d=item["pnl_7d"],
            win_rate=item["win_rate"],
            max_drawdown=item["max_drawdown"],
            trade_count=item["trade_count"],
            is_top_10=item["is_top_10"],
            is_selected=item["is_selected"],
            snapshot_at=now,
        ))
    database.insert_agent_snapshots(snapshots)
    print(f"写入 {len(snapshots)} 条最新 Agent 快照")

    # 写入模拟 Token
    for item in MOCK_TOKENS:
        token = Token(
            token_address=item["token_address"],
            symbol=item["symbol"],
            name=item["name"],
            pool_address=item["pool_address"],
            chain=item["chain"],
            created_at=now,
            updated_at=now,
        )
        database.upsert_token(token)
    print(f"写入 {len(MOCK_TOKENS)} 个 Token")

    # 写入模拟市场快照
    market_snapshots = []
    for item in MOCK_TOKENS:
        market_snapshots.append(TokenMarketSnapshot(
            token_address=item["token_address"],
            price_usd=item["price_usd"],
            liquidity_usd=item["liquidity_usd"],
            volume_1h=item["volume_1h"],
            volume_24h=item["volume_24h"],
            price_change_1h=item["price_change_1h"],
            price_change_24h=item["price_change_24h"],
            buy_slippage=item["buy_slippage"],
            sell_slippage=item["sell_slippage"],
            holder_count=item["holder_count"],
            top_10_holder_pct=item["top_10_holder_pct"],
            snapshot_at=now,
        ))
    database.insert_market_snapshots(market_snapshots)
    print(f"写入 {len(market_snapshots)} 条市场快照")

    # 写入模拟 AI Pot
    pot = AIPotRound(
        round_id="round_001",
        round_start="2026-04-21T00:00:00Z",
        round_end="2026-04-28T00:00:00Z",
        status="active",
        selected_agents=json.dumps(["agent_001", "agent_002", "agent_003"]),
        pot_pnl=12.5,
        created_at=now,
        updated_at=now,
    )
    database.upsert_ai_pot_round(pot)
    print("写入 1 条 AI Pot 记录")

    # 写入系统事件
    database.insert_system_event(SystemEvent(
        event_id=build_event_id(),
        module="system",
        level="info",
        event="db_initialized",
        detail="数据库初始化完成，模拟数据已写入",
        trace_id="",
        created_at=now,
    ))
    print("初始化完成")


if __name__ == "__main__":
    main()

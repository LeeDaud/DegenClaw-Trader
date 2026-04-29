"""预判引擎 — 检测 Agent 大涨/大跌信号"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from db.database import Database
from db.models import Alert, utc_now_iso


SIGNAL_THRESHOLDS = {
    "rank_surge_min": -5,       # 排名提升超过 N 位（rank 值变小 = 排名上升）
    "rank_dump_min": 5,         # 排名下降超过 N 位
    "pnl_surge_min_24h": 8.0,   # 24h PnL 超过此值视为大涨
    "pnl_dump_max_24h": -8.0,   # 24h PnL 低于此值视为大跌
    "volume_spike_ratio": 3.0,  # 成交量增长倍数
    "price_surge_min_1h": 10.0,  # 1h 涨幅
    "price_dump_max_1h": -8.0,  # 1h 跌幅
    "combined_surge_score": 35,  # 综合看涨信号分（原 25，提高减少误报）
    "combined_dump_score": 35,  # 综合看跌信号分（原 25）
}

# 同一 Agent 同一类型的预警冷却时间（秒）
ALERT_COOLDOWN_SECONDS = 21600  # 6 小时


class SignalEngine:
    def __init__(self, database: Database) -> None:
        self.database = database

    def run_check(self) -> list[Alert]:
        """对所有 Agent 执行一轮信号检测，返回新生成的预警"""
        now = utc_now_iso()
        alerts: list[Alert] = []

        agents = self.database.list_agents(limit=200)
        for agent in agents:
            agent_id = agent["agent_id"]
            agent_name = agent["name"]

            # 读取最近 3 条快照用于趋势分析
            snapshots = self.database.get_agent_snapshots(agent_id, limit=3)
            if len(snapshots) < 2:
                continue

            latest = snapshots[0]  # 最新
            prev = snapshots[1]    # 上一个

            # 读取市场数据（如果有）
            market = None
            if agent.get("token_address"):
                market = self.database.get_latest_market_snapshot(agent["token_address"])

            # 分析各维度信号
            signals = self._analyze(agent_id, agent_name, latest, prev, market, snapshots)

            for sig in signals:
                # 去重检查：同一 Agent + 同一类型在冷却期内不重复预警
                if self._has_recent_alert(agent_id, sig["type"]):
                    continue

                alert_id = f"alert_{uuid4().hex[:16]}"
                alert_id = f"alert_{uuid4().hex[:16]}"
                alert = Alert(
                    alert_id=alert_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    alert_type=sig["type"],
                    severity=sig["severity"],
                    title=sig["title"],
                    detail=sig["detail"],
                    score=sig["score"],
                    snapshot_data=json.dumps({
                        "latest_snapshot": {k: str(v) for k, v in latest.items()} if latest else {},
                        "prev_snapshot": {k: str(v) for k, v in prev.items()} if prev else {},
                        "market": {k: str(v) for k, v in market.items()} if market else {},
                    }, ensure_ascii=False),
                    notified=False,
                    created_at=now,
                )
                self.database.insert_alert(alert)
                alerts.append(alert)

        return alerts

    def _has_recent_alert(self, agent_id: str, alert_type: str) -> bool:
        """检查冷却期内是否已存在同类预警"""
        existing = self.database.list_alerts(
            limit=10, agent_id=agent_id, alert_type=alert_type,
        )
        if not existing:
            return False
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for alert in existing:
            try:
                created = datetime.fromisoformat(alert["created_at"].replace("Z", "+00:00"))
                if (now - created).total_seconds() < ALERT_COOLDOWN_SECONDS:
                    return True
            except (ValueError, KeyError):
                continue
        return False

    def _analyze(
        self,
        agent_id: str,
        agent_name: str,
        latest: dict[str, Any],
        prev: dict[str, Any],
        market: dict[str, Any] | None,
        snapshots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        rank_change = (prev.get("rank", 0) or 0) - (latest.get("rank", 0) or 0)
        pnl_24h = float(latest.get("pnl_24h", 0) or 0)
        pnl_7d = float(latest.get("pnl_7d", 0) or 0)
        prev_pnl_7d = float(prev.get("pnl_7d", 0) or 0)
        win_rate = float(latest.get("win_rate", 0) or 0)
        prev_win_rate = float(prev.get("win_rate", 0) or 0)
        drawdown = float(latest.get("max_drawdown", 0) or 0)

        # === 1. 排名飙升 ===
        if rank_change >= SIGNAL_THRESHOLDS["rank_surge_min"] and rank_change < 0:
            signals.append({
                "type": "rank_surge",
                "severity": "high" if abs(rank_change) >= 10 else "medium",
                "title": f"{agent_name} 排名飙升",
                "detail": f"排名从 #{prev['rank']} 上升至 #{latest['rank']}（↑{abs(rank_change)} 位）",
                "score": float(abs(rank_change) * 3),
            })

        # === 2. 排名暴跌 ===
        if rank_change >= SIGNAL_THRESHOLDS["rank_dump_min"] and rank_change > 0:
            signals.append({
                "type": "rank_dump",
                "severity": "critical" if abs(rank_change) >= 10 else "high",
                "title": f"{agent_name} 排名暴跌",
                "detail": f"排名从 #{prev['rank']} 下降至 #{latest['rank']}（↓{rank_change} 位）",
                "score": float(abs(rank_change) * 3),
            })

        # === 3. 收益暴涨 ===
        if pnl_24h >= SIGNAL_THRESHOLDS["pnl_surge_min_24h"]:
            signals.append({
                "type": "surge",
                "severity": "high" if pnl_24h >= 15 else "medium",
                "title": f"{agent_name} 收益暴涨",
                "detail": f"24h PnL +{pnl_24h}%，7d PnL {pnl_7d:+.1f}%，胜率 {win_rate}%",
                "score": pnl_24h * 2,
            })

        # === 4. 收益暴跌 ===
        if pnl_24h <= SIGNAL_THRESHOLDS["pnl_dump_max_24h"]:
            signals.append({
                "type": "dump",
                "severity": "high" if pnl_24h <= -15 else "medium",
                "title": f"{agent_name} 收益暴跌",
                "detail": f"24h PnL {pnl_24h}%，7d PnL {pnl_7d:+.1f}%，最大回撤 {drawdown}%",
                "score": abs(pnl_24h) * 2,
            })

        # === 5. 成交量异常（需要市场数据） ===
        if market:
            vol_24h = float(market.get("volume_24h", 0) or 0)
            vol_1h = float(market.get("volume_1h", 0) or 0)
            price_change_1h = float(market.get("price_change_1h", 0) or 0)
            price_change_24h = float(market.get("price_change_24h", 0) or 0)

            if vol_1h > 0 and vol_24h > 0 and (vol_1h * 24) > vol_24h * SIGNAL_THRESHOLDS["volume_spike_ratio"]:
                signals.append({
                    "type": "volume_spike",
                    "severity": "medium",
                    "title": f"{agent_name} 成交量异常",
                    "detail": f"1h 成交量 ${vol_1h:,.0f}，24h ${vol_24h:,.0f}，短线放量 {((vol_1h * 24) / vol_24h - 1) * 100:.0f}%",
                    "score": min(((vol_1h * 24) / vol_24h) * 5, 30),
                })

            if price_change_1h >= SIGNAL_THRESHOLDS["price_surge_min_1h"]:
                signals.append({
                    "type": "price_surge",
                    "severity": "high" if price_change_1h >= 20 else "medium",
                    "title": f"{agent_name} Token 价格暴涨",
                    "detail": f"1h 涨幅 +{price_change_1h}%，24h 涨幅 {price_change_24h:+.1f}%",
                    "score": price_change_1h * 1.5,
                })

            if price_change_1h <= SIGNAL_THRESHOLDS["price_dump_max_1h"]:
                signals.append({
                    "type": "price_dump",
                    "severity": "high" if price_change_1h <= -15 else "medium",
                    "title": f"{agent_name} Token 价格暴跌",
                    "detail": f"1h 跌幅 {price_change_1h}%，24h 跌幅 {price_change_24h:+.1f}%",
                    "score": abs(price_change_1h) * 1.5,
                })

        # === 6. 综合看涨：多项正面信号叠加 ===
        combined_up = 0
        combined_up_reasons: list[str] = []
        if rank_change < 0:
            combined_up += abs(rank_change) * 2
            combined_up_reasons.append(f"排名↑{abs(rank_change)}")
        if pnl_7d > prev_pnl_7d:
            combined_up += 5
            combined_up_reasons.append(f"7d PnL 改善 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if win_rate > prev_win_rate:
            combined_up += 3
            combined_up_reasons.append(f"胜率上升 ({prev_win_rate}%→{win_rate}%)")
        if pnl_24h > 5:
            combined_up += 5
            combined_up_reasons.append(f"24h PnL 强劲 (+{pnl_24h}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) > 10:
                combined_up += 5
                combined_up_reasons.append("Token 价格趋势向好")
            if float(market.get("volume_24h", 0) or 0) > 0:
                combined_up += 2

        if combined_up >= SIGNAL_THRESHOLDS["combined_surge_score"]:
            signals.append({
                "type": "combined_surge",
                "severity": "critical" if combined_up >= 40 else "high",
                "title": f"{agent_name} 综合看涨信号",
                "detail": " | ".join(combined_up_reasons),
                "score": combined_up,
            })

        # === 7. 综合看跌：多项负面信号叠加 ===
        combined_down = 0
        combined_down_reasons: list[str] = []
        if rank_change > 0:
            combined_down += rank_change * 2
            combined_down_reasons.append(f"排名↓{rank_change}")
        if pnl_7d < prev_pnl_7d:
            combined_down += 5
            combined_down_reasons.append(f"7d PnL 恶化 ({prev_pnl_7d:+.1f}→{pnl_7d:+.1f})")
        if win_rate < prev_win_rate:
            combined_down += 3
            combined_down_reasons.append(f"胜率下降 ({prev_win_rate}%→{win_rate}%)")
        if pnl_24h < -3:
            combined_down += 5
            combined_down_reasons.append(f"24h PnL 为负 ({pnl_24h}%)")
        if drawdown < -10:
            combined_down += 3
            combined_down_reasons.append(f"回撤过大 ({drawdown}%)")
        if market:
            if float(market.get("price_change_24h", 0) or 0) < -5:
                combined_down += 5
                combined_down_reasons.append("Token 价格走弱")

        if combined_down >= SIGNAL_THRESHOLDS["combined_dump_score"]:
            signals.append({
                "type": "combined_dump",
                "severity": "critical" if combined_down >= 40 else "high",
                "title": f"{agent_name} 综合看跌信号",
                "detail": " | ".join(combined_down_reasons),
                "score": combined_down,
            })

        return signals

"""AI Pot PnL 监控引擎 — 比对快照 → 超阈值 → 涨跌预判"""

from __future__ import annotations

import logging
from typing import Any

from db.database import Database

logger = logging.getLogger(__name__)


class PotPnlMonitor:
    """监控 PotSubAgent 的 PnL 变化，超阈值时返回变更列表"""

    def __init__(self, database: Database) -> None:
        self.database = database

    def check_sub_pot_changes(
        self,
        round_id: str,
        sub_pots: list[dict[str, Any]],
        pnl_threshold: float = 10.0,
        roi_threshold: float = 5.0,
    ) -> list[dict[str, Any]]:
        """遍历所有 sub_pot，对比最近两次快照，返回超阈值变更列表"""
        changes: list[dict[str, Any]] = []
        for sp in sub_pots:
            snapshots = self.database.get_pot_pnl_snapshots(sp["sub_pot_id"], limit=3)
            if len(snapshots) < 2:
                continue

            latest = snapshots[0]
            prev = snapshots[-1]

            # PnL 绝对值变化
            pnl_change = latest["final_pnl"] - prev["final_pnl"]
            prev_pnl = prev["final_pnl"]
            pnl_change_pct = (
                (pnl_change / abs(prev_pnl)) * 100 if prev_pnl != 0 else 0.0
            )

            # ROI 变化
            starting = sp.get("starting_capital", 0) or 0
            latest_roi = (
                (latest["current_value"] / starting - 1) * 100 if starting else 0
            )
            prev_roi = (
                (prev["current_value"] / starting - 1) * 100 if starting else 0
            )
            roi_change = latest_roi - prev_roi

            direction = self._predict_direction(snapshots)

            change_pct = abs(pnl_change_pct)
            change_roi = abs(roi_change)
            if change_pct >= pnl_threshold or change_roi >= roi_threshold:
                changes.append({
                    "sub_pot_id": sp["sub_pot_id"],
                    "name": sp["name"],
                    "agent_name": sp.get("agent_name", ""),
                    "pnl_before": round(prev_pnl, 2),
                    "pnl_now": round(latest["final_pnl"], 2),
                    "pnl_change": round(pnl_change, 2),
                    "pnl_change_pct": round(pnl_change_pct, 2),
                    "roi_before": round(prev_roi, 2),
                    "roi_now": round(latest_roi, 2),
                    "roi_change": round(roi_change, 2),
                    "direction": direction,
                    "severity": (
                        "high" if max(change_pct, change_roi) >= pnl_threshold * 2
                        else "medium"
                    ),
                })

        return changes

    def _predict_direction(
        self, snapshots: list[dict[str, Any]]
    ) -> str:
        """基于最近快照判定涨跌趋势（最多取 3 个点）"""
        if len(snapshots) < 2:
            return "unknown"

        pnls = [s["final_pnl"] for s in snapshots[:3]]

        if len(pnls) >= 3:
            if pnls[0] > pnls[1] > pnls[2]:
                return "up"
            if pnls[0] < pnls[1] < pnls[2]:
                return "down"
            if pnls[0] > pnls[1] and pnls[1] < pnls[2]:
                return "recovery_up"
            if pnls[0] < pnls[1] and pnls[1] > pnls[2]:
                return "pullback_down"
            return "stable"

        # 仅 2 个快照
        diff = pnls[0] - pnls[1]
        return "up" if diff > 0 else ("down" if diff < 0 else "stable")

    @staticmethod
    def build_feishu_card(change: dict[str, Any]) -> dict:
        """为 PnL 变更构建飞书消息卡片"""
        direction_icons = {
            "up": "🟢",
            "down": "🔴",
            "recovery_up": "🟢↗",
            "pullback_down": "🔴↘",
            "stable": "⚪",
            "unknown": "❓",
        }
        icon = direction_icons.get(change["direction"], "❓")
        severity_color = "red" if change["severity"] == "high" else "orange"

        elements = [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**子池：** {change['name']}（{change.get('agent_name', '')}）"}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**方向预判：** {icon} {change['direction']} | **严重程度：** {change['severity']}"}},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": (
                f"**PnL 变化：** {change['pnl_before']} → {change['pnl_now']}（{change['pnl_change_pct']}%）\n"
                f"**ROI 变化：** {change['roi_before']}% → {change['roi_now']}%（{change['roi_change']}%）\n"
                f"**PnL 绝对值：** {change['pnl_change']}"
            )}},
            {"tag": "hr"},
            {"tag": "note", "element": {"tag": "plain_text", "content": "DegenClaw AI Pot Monitor"}},
        ]

        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"{icon} Pot PnL 变动 · {change['name']}"},
                "template": severity_color,
            },
            "elements": elements,
        }

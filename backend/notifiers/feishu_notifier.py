"""飞书机器人通知器 — 通过 webhook 发送预警卡片"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 信号类型 → 颜色
SEVERITY_COLORS = {
    "critical": "red",
    "high": "orange",
    "medium": "yellow",
    "low": "blue",
}

CARD_HEADER_TEMPLATES = {
    "surge": {"title": "🚀 大涨预警", "color": "green"},
    "dump": {"title": "📉 大跌预警", "color": "red"},
    "rank_surge": {"title": "⬆️ 排名飙升", "color": "green"},
    "rank_dump": {"title": "⬇️ 排名暴跌", "color": "red"},
    "volume_spike": {"title": "⚡ 成交量异常", "color": "orange"},
    "price_surge": {"title": "📈 Token 价格暴涨", "color": "green"},
    "price_dump": {"title": "📉 Token 价格暴跌", "color": "red"},
    "combined_surge": {"title": "🟢 综合看涨信号", "color": "green"},
    "combined_dump": {"title": "🔴 综合看跌信号", "color": "red"},
}

# 全局限速：两次批量发送之间至少间隔（秒）
RATE_LIMIT_INTERVAL = 30  # 30 秒内最多发一批

# 内存去重缓存 TTL（秒）— 防止同一条 alert_id 被重复发送
DEDUP_TTL = 300  # 5 分钟


def _build_card(alert: dict[str, Any]) -> dict:
    """构建飞书消息卡片"""
    atype = alert.get("alert_type", "surge")
    header_info = CARD_HEADER_TEMPLATES.get(atype, {"title": "⚠️ 预警", "color": "yellow"})
    severity = alert.get("severity", "medium")
    color = SEVERITY_COLORS.get(severity, "yellow")

    elements: list[dict] = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**Agent：** {alert['agent_name']}（`{alert['agent_id']}`）"},
        },
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**信号强度：** {alert['score']} | **严重程度：** {severity}"},
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**详情：**\n{alert['detail']}"},
        },
    ]

    # 解析快照数据附加到卡片
    try:
        snapshot = json.loads(alert.get("snapshot_data", "{}"))
        if snapshot.get("latest_snapshot"):
            s = snapshot["latest_snapshot"]
            lines = [
                f"排名：**#{s.get('rank', '?')}**",
                f"24h PnL：**{s.get('pnl_24h', '?')}%**",
                f"7d PnL：**{s.get('pnl_7d', '?')}%**",
                f"胜率：**{s.get('win_rate', '?')}%**",
            ]
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**当前状态**\n" + "\n".join(lines)},
            })
    except (json.JSONDecodeError, KeyError):
        pass

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "note",
        "element": {
            "tag": "plain_text",
            "content": f"DegenClaw Alpha Engine · {alert.get('created_at', '')[:19]}",
        },
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{header_info['title']} · {alert['agent_name']}"},
            "template": color,
        },
        "elements": elements,
    }


class FeishuNotifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self.webhook_url = webhook_url
        self._last_send_at: float = 0.0  # 上次发送时间戳
        self._dedup_cache: set[str] = set()  # 已发送 alert_id 集合

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def _check_rate_limit(self) -> bool:
        """全局限速检查：两次发送至少间隔 RATE_LIMIT_INTERVAL 秒"""
        now = time.monotonic()
        if now - self._last_send_at < RATE_LIMIT_INTERVAL:
            logger.warning("全局限速触发，跳过本次发送（距上次仅 %.0fs）", now - self._last_send_at)
            return False
        return True

    def _check_dedup(self, alert_id: str) -> bool:
        """内存去重检查：同一条 alert_id 在 DEDUP_TTL 内不重复发送"""
        if alert_id in self._dedup_cache:
            logger.debug("去重跳过已发送预警: %s", alert_id)
            return False
        self._dedup_cache.add(alert_id)
        return True

    def _trim_dedup_cache(self) -> None:
        """裁剪去重缓存（惰性，超过 500 条时清理一半）"""
        if len(self._dedup_cache) > 500:
            # 简单裁剪：保留最近添加的一半
            self._dedup_cache = set(list(self._dedup_cache)[-250:])

    def send_alert(self, alert: dict[str, Any]) -> bool:
        """发送单条预警，返回是否成功"""
        if not self.webhook_url:
            logger.warning("飞书 webhook 未配置，跳过通知")
            return False

        if not self._check_dedup(alert.get("alert_id", "")):
            return False

        card = _build_card(alert)
        payload = {"msg_type": "interactive", "card": card}

        try:
            resp = httpx.post(
                self.webhook_url,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            if result.get("code") == 0:
                logger.info("飞书通知发送成功: %s - %s", alert["alert_type"], alert["agent_name"])
                return True
            else:
                logger.error("飞书通知 API 返回错误: %s", result)
                return False
        except httpx.HTTPError as exc:
            logger.error("飞书通知 HTTP 请求失败: %s", exc)
            return False

    def send_alerts_batch(self, alerts: list[dict[str, Any]]) -> int:
        """批量发送，返回成功数（受全局限速控制）"""
        if not alerts:
            return 0

        # 全局限速
        if not self._check_rate_limit():
            return 0

        self._last_send_at = time.monotonic()
        self._trim_dedup_cache()

        success = 0
        for alert in alerts:
            if self.send_alert(alert):
                success += 1

        # 如果全部成功，冷却时间加倍避免持续冲击
        if success == len(alerts):
            self._last_send_at += RATE_LIMIT_INTERVAL

        return success

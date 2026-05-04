"""烛图反转分析器 — 检测价格连续上涨/下跌后的反转信号"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from db.models import Alert, utc_now_iso
from uuid import uuid4

logger = logging.getLogger(__name__)

# 价格变化阈值（小于此值视为 flat，过滤噪声）
PRICE_CHANGE_THRESHOLD_PCT = 0.1

# 最小趋势连续根数（低于此不算趋势）
MIN_TREND_LENGTH = 3

# 触发反转预警的连续反向根数
REVERSAL_LEVELS = (1, 3, 5)

# 每级别冷却（秒）
LEVEL_COOLDOWN_SECONDS = 900  # 15 分钟

# 反转回撤比例底限（宽松）：反转幅度需达到趋势幅度的 15%，否则转由噪声底限判断
MIN_RETRACEMENT_RATIO = 0.15

# 噪声底限置信度：1σ ≈ 68%，宁可误报不错过
NOISE_FLOOR_Z = 1.0

# 趋势强度分级
TREND_STRENGTH_BANDS = [
    (12, 3.0),   # 12+ → ×3.0
    (8, 2.0),    # 8~11 → ×2.0
    (5, 1.5),    # 5~7 → ×1.5
    (3, 1.0),    # 3~4 → ×1.0
]

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def _trend_strength(length: int) -> float:
    for threshold, factor in TREND_STRENGTH_BANDS:
        if length >= threshold:
            return factor
    return 1.0


def _escalate(sev: str, levels: int) -> str:
    idx = SEVERITY_ORDER.index(sev)
    return SEVERITY_ORDER[min(idx + levels, len(SEVERITY_ORDER) - 1)]


def _calc_severity(reversal_count: int, trend_length: int) -> str:
    base_map = {1: "low", 3: "medium", 5: "high"}
    base = base_map.get(reversal_count, "low")
    strength = _trend_strength(trend_length)
    if strength >= 3.0:
        return _escalate(base, 2)
    if strength >= 2.0:
        return _escalate(base, 1)
    return base


def _calc_noise_floor(prices: list[float], z: float = NOISE_FLOOR_Z) -> float:
    """计算价格序列的动态噪声底限 = Z × 相邻变动百分比的标准差

    反映该 token 自身的近期波动水平：
      - 低波动 token → 底限低，对小反转敏感
      - 高波动 token → 底限高，屏蔽随机摇摆

    Args:
        prices: 有效价格列表（已过滤 flat），[最新, ..., 最旧]
        z: Z 值，默认 2.0 ≈ 95% 置信度

    Returns:
        噪声底限（百分比），至少 0.2%
    """
    if len(prices) < 4:
        return 0.5  # 样本不足，保守回退

    changes = []
    for i in range(len(prices) - 1):
        older = prices[i + 1]
        newer = prices[i]
        if older > 0 and newer > 0:
            pct = abs((newer - older) / older * 100)
            changes.append(pct)

    if len(changes) < 3:
        return 0.5

    n = len(changes)
    mean = sum(changes) / n
    variance = sum((c - mean) ** 2 for c in changes) / n
    std = math.sqrt(variance) if variance > 0 else 0.2
    return round(max(std * z, 0.2), 4)


class CandleAnalyzer:
    """烛图模式检测 + 反转预警

    每次采集周期对每个 token 的价格序列进行分析：
      1. 计算相邻 tick 的价格方向（过滤 flat）
      2. 从最新向旧扫描：反转段连续根数 → 前趋趋势连续根数
      3. 反转根数 ∈ {1,3,5} 且趋势根数 ≥ 3 → 预警
      4. 严重度 = 反转基础等级 × 趋势强度系数
    """

    def __init__(self, database: Any) -> None:
        self.database = database
        self._last_alert: dict[str, float] = {}  # "token:level" → timestamp

    def run_check(self) -> list[Alert]:
        """对当前活跃 token 逐一分析，返回新生成的 Alert 列表"""
        alerts: list[Alert] = []

        token_addresses = self._get_active_token_addresses()
        if not token_addresses:
            return alerts

        now = utc_now_iso()
        for addr in token_addresses:
            try:
                alert = self._check_token(addr, now)
                if alert:
                    alerts.append(alert)
            except Exception:
                logger.exception("candle analyze failed for %s", addr)

        if alerts:
            # 清理过旧 tick 数据（每日仅执行一次惰性清理）
            self.database.cleanup_old_price_ticks(keep_hours=1)

        return alerts

    def _get_active_token_addresses(self) -> list[str]:
        agents = self.database.list_agents(limit=500)
        addrs = list({a["token_address"] for a in agents if a.get("token_address")})
        return addrs

    def _check_token(self, token_address: str, now: str) -> Alert | None:
        ticks = self.database.get_price_ticks(token_address, limit=50)
        if len(ticks) < 8:
            return None

        prices = [t["price_usd"] for t in ticks]
        volumes = [t["volume_1h"] for t in ticks]

        result = self._analyze_series(prices, volumes)
        if not result:
            return None

        # 冷却检查
        level = result["reversal_count"]
        if not self._can_alert(token_address, level):
            return None

        # 找对应 Agent
        agents = self.database.list_agents(limit=500)
        agent = next((a for a in agents if a["token_address"] == token_address), None)
        if not agent:
            return None

        alert = self._build_alert(agent, result, now)
        self.database.insert_alert(alert, cooldown_seconds=LEVEL_COOLDOWN_SECONDS * 2)
        self._mark_alerted(token_address, level)
        return alert

    # ── 核心分析 ──────────────────────────────────────────────────

    @staticmethod
    def _analyze_series(prices: list[float], volumes: list[float]) -> dict | None:
        """分析价格序列，检测趋势+反转模式

        Args:
            prices: [最新, ..., 最旧]，索引 0 为最新
            volumes: 对应位置的 volume_1h

        Returns:
            dict(方向, 严重度, 反转根数, 趋势长度, 涨跌幅, 成交量) 或 None
        """
        if len(prices) < 6:
            return None

        # 1. 计算每对相邻 tick 的方向（过滤 flat）
        dirs: list[str] = []
        valid_prices: list[float] = []
        valid_volumes: list[float] = []

        for i in range(len(prices) - 1):
            older = prices[i + 1]
            newer = prices[i]
            if older <= 0 or newer <= 0:
                continue
            change_pct = (newer - older) / older * 100
            if abs(change_pct) < PRICE_CHANGE_THRESHOLD_PCT:
                continue
            dirs.append("up" if change_pct > 0 else "down")
            valid_prices.append(newer)
            valid_volumes.append(volumes[i] if i < len(volumes) else 0.0)

        if len(dirs) < 4:
            return None

        # 2. 从最新（dirs[0]）开始找反转段
        reversal_dir = dirs[0]
        reversal_count = 0
        for d in dirs:
            if d == reversal_dir:
                reversal_count += 1
            else:
                break

        # 全部同向 → 无反转
        if reversal_count >= len(dirs):
            return None

        # 3. 反转段之后的第一个不同方向 → 趋势段
        trend_dir = dirs[reversal_count]
        trend_length = 0
        for d in dirs[reversal_count:]:
            if d == trend_dir:
                trend_length += 1
            else:
                break

        # 4. 判断条件
        if trend_length < MIN_TREND_LENGTH:
            return None

        # 只触发精确匹配的反转根数
        if reversal_count not in REVERSAL_LEVELS:
            return None

        is_bearish = trend_dir == "up" and reversal_dir == "down"
        is_bullish = trend_dir == "down" and reversal_dir == "up"
        if not is_bearish and not is_bullish:
            return None

        # 5. 涨跌幅计算
        #    方向序列 dirs[0..R-1] = 反转段（R=reversal_count），涉及 R+1 个价格
        #    dirs[R..R+T-1] = 趋势段（T=trend_length），涉及 T+1 个价格
        #    价格索引关系：
        #      反转段：最新价 valid_prices[0] → 最旧价 valid_prices[R]
        #      趋势段：最新价 valid_prices[R] → 最旧价 valid_prices[R+T]
        r_recent = valid_prices[0]
        r_oldest = valid_prices[min(reversal_count, len(valid_prices) - 1)]
        t_recent = valid_prices[min(reversal_count, len(valid_prices) - 1)]
        t_oldest = valid_prices[min(reversal_count + trend_length, len(valid_prices) - 1)]

        price_change_trend_pct = (t_recent - t_oldest) / t_oldest * 100
        price_change_reversal_pct = (r_recent - r_oldest) / r_oldest * 100

        # 8. 双阈值过滤：宽松比例（15%）+ 动态噪声底限（2σ），任一即放行
        trend_magnitude = abs(price_change_trend_pct)
        reversal_magnitude = abs(price_change_reversal_pct)
        if trend_magnitude > 0:
            noise_floor = _calc_noise_floor(valid_prices)
            below_ratio = reversal_magnitude < trend_magnitude * MIN_RETRACEMENT_RATIO
            below_noise = reversal_magnitude < noise_floor
            if below_ratio and below_noise:
                return None  # 两种阈值都没过 → 视为随机噪声

        # 6. 反转段成交量（取最大值）
        reversal_volumes = valid_volumes[:reversal_count]
        volume_at_reversal = max(reversal_volumes) if reversal_volumes else 0.0

        # 7. 严重度 + 方向
        severity = _calc_severity(reversal_count, trend_length)
        direction = "bearish" if is_bearish else "bullish"

        # 9. 全局方向判断：整体窗口明显单边时同向"反转"是噪声
        #    例：全程 80% 上涨 +24%，最新 5 根上涨不是"下跌后的反转"而是上涨延续
        if len(dirs) >= 6:
            up_ratio = sum(1 for d in dirs if d == "up") / len(dirs)
            full_change = (valid_prices[0] - valid_prices[-1]) / valid_prices[-1] * 100
            if direction == "bullish" and up_ratio > 0.6 and full_change > 5:
                return None
            if direction == "bearish" and (1 - up_ratio) > 0.6 and full_change < -5:
                return None

        return {
            "direction": direction,
            "severity": severity,
            "reversal_count": reversal_count,
            "trend_length": trend_length,
            "trend_dir": trend_dir,
            "price_change_trend_pct": round(price_change_trend_pct, 2),
            "price_change_reversal_pct": round(price_change_reversal_pct, 2),
            "volume_at_reversal": round(volume_at_reversal, 2),
        }

    # ── 冷却 ──────────────────────────────────────────────────────

    def _can_alert(self, token_address: str, level: int) -> bool:
        now = time.time()
        key = f"{token_address}:{level}"
        last = self._last_alert.get(key, 0.0)
        if now - last < LEVEL_COOLDOWN_SECONDS:
            return False
        return True

    def _mark_alerted(self, token_address: str, level: int) -> None:
        key = f"{token_address}:{level}"
        self._last_alert[key] = time.time()

        # 惰性裁剪冷却缓存（超过 1000 条时清理一半）
        if len(self._last_alert) > 1000:
            # 保留最近的 500 条
            sorted_items = sorted(self._last_alert.items(), key=lambda x: x[1], reverse=True)
            self._last_alert = dict(sorted_items[:500])

    def reset_cooldown(self, token_address: str | None = None) -> None:
        """重置冷却（调试/测试用）"""
        if token_address:
            keys = [k for k in self._last_alert if k.startswith(f"{token_address}:")]
            for k in keys:
                del self._last_alert[k]
        else:
            self._last_alert.clear()

    # ── Alert 构建 ────────────────────────────────────────────────

    @staticmethod
    def _build_alert(agent: dict, result: dict, now: str) -> Alert:
        direction = result["direction"]
        rc = result["reversal_count"]
        tl = result["trend_length"]
        trend_dir_cn = "上涨" if result["trend_dir"] == "up" else "下跌"
        reversal_dir_cn = "回调" if direction == "bearish" else "反弹"
        severity = result["severity"]

        type_labels = {
            "bearish": "reversal_bearish",
            "bullish": "reversal_bullish",
        }

        title = (
            f"{agent['name']} {'连续上涨后' if direction == 'bearish' else '连续下跌后'}"
            f"出现{rc}根{reversal_dir_cn}"
        )

        detail = (
            f"趋势：连续 {tl} 根{trend_dir_cn}（{result['price_change_trend_pct']:+.2f}%）\n"
            f"反转：连续 {rc} 根{reversal_dir_cn}（{result['price_change_reversal_pct']:+.2f}%）\n"
            f"反转段成交量：${result['volume_at_reversal']:,.2f}"
        )

        alert_id = f"candle_{uuid4().hex[:16]}"
        return Alert(
            alert_id=alert_id,
            agent_id=agent["agent_id"],
            agent_name=agent["name"],
            alert_type=type_labels[direction],
            severity=severity,
            title=title,
            detail=detail,
            score=float(rc * tl),
            snapshot_data='{}',
            notified=False,
            created_at=now,
        )

    def clear_alerts(self) -> None:
        """清空冷却缓存"""
        self._last_alert.clear()

"""DegenClaw 评分引擎"""

from __future__ import annotations

import logging
from typing import Any

from db.database import Database
from db.models import AgentScore, utc_now_iso
from scoring.config import load_config

logger = logging.getLogger(__name__)


def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def _compute_grade(total: int) -> str:
    if total >= 70:
        return "A"
    if total >= 55:
        return "B"
    if total >= 40:
        return "C"
    if total >= 25:
        return "D"
    if total >= 15:
        return "E"
    return "F"


def _determine_label(total: int, risk_penalty: int) -> str:
    if risk_penalty <= -5:
        return "risk_alert"
    if total >= 70:
        return "hot_candidate"
    if total >= 55:
        return "candidate"
    if total >= 40:
        return "high_watch"
    if total >= 25:
        return "watch"
    return "ignore"


def _pick(config_list: list[dict], value: float, key_min: str = "min_rank", key_score: str = "score") -> int:
    """从阈值列表中找到第一个匹配的分数"""
    for item in config_list:
        if value >= item.get(key_min, 0):
            return item[key_score]
    return 0


INVALID = object()


def _lookup(cfg: dict, *keys: str) -> Any:
    """安全地按路径查找嵌套配置"""
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict):
            return INVALID
        cur = cur.get(k, INVALID)
        if cur is INVALID:
            return INVALID
    return cur


class DegenClawScoreEngine:
    """多维度评分引擎 — 0-100 分 + 风险扣分"""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.cfg = load_config()

    # ---- 公开方法 ----

    def run_round(self, season_start: str | None = None, season_end: str | None = None) -> list[AgentScore]:
        """对所有 Agent 执行一轮评分"""
        agents = self.database.list_agents(limit=500, season_start=season_start, season_end=season_end)
        now = utc_now_iso()
        results: list[AgentScore] = []

        for agent in agents:
            agent_id = agent["agent_id"]
            token_address = agent.get("token_address", "")

            # 读取最近 10 条快照（用于趋势分析）
            snapshots = self.database.get_agent_snapshots(agent_id, limit=10)

            # 读取最新市场快照
            market = self.database.get_latest_market_snapshot(token_address) if token_address else None

            score = self._score_one(agent, snapshots, market, now)
            results.append(score)

        logger.info("评分完成: %d 个 Agent", len(results))
        return results

    def _score_one(
        self,
        agent: dict[str, Any],
        snapshots: list[dict[str, Any]],
        market: dict[str, Any] | None,
        now: str,
    ) -> AgentScore:
        agent_id = agent["agent_id"]
        token_address = agent.get("token_address", "")

        # 各维度评分
        council, council_reasons = self._council_prob(snapshots)
        trading, trading_reasons = self._trading_perf(snapshots)
        rank, rank_reasons = self._rank_trend(snapshots)
        token_market, market_reasons = self._token_market(market, agent.get("token_address", ""))
        visibility = self._visibility(snapshots)
        risk = self._risk_penalty(market)
        risk_reasons = self._risk_reasons(market)

        total = _clamp(council + trading + rank + token_market + visibility + risk, 0, 100)
        grade = _compute_grade(total)
        label = _determine_label(total, risk)

        # 构建原因文本
        reasons = council_reasons + trading_reasons + rank_reasons + market_reasons + risk_reasons
        reason_str = "; ".join(reasons) if reasons else "数据不足，基础分"

        return AgentScore(
            agent_id=agent_id,
            token_address=token_address,
            score_total=total,
            council_probability_score=council,
            trading_performance_score=trading,
            rank_trend_score=rank,
            token_market_score=token_market,
            visibility_score=visibility,
            risk_penalty=risk,
            grade=grade,
            label=label,
            reason=reason_str,
            scored_at=now,
        )

    # ---- AI Council 入选概率 (0-35) ----

    def _council_prob(self, snapshots: list[dict[str, Any]]) -> tuple[int, list[str]]:
        """AI Council 入选概率 (0-35)"""
        reasons: list[str] = []
        if not snapshots:
            return 0, reasons

        latest = snapshots[0]
        rank = latest.get("rank", 0)
        cfg = self.cfg.get("council", {})

        # 排名接近 top 10 (0-15)
        rank_thresholds = cfg.get("rank_score", {}).get("thresholds", [])
        rank_score = 0
        for t in rank_thresholds:
            if rank <= t.get("max_rank", 999):
                rank_score = t.get("score", 0)
                break
        if rank_score > 0:
            reasons.append(f"排名#{rank}")

        # 历史入选加分 (0-10)
        selected_count = sum(1 for s in snapshots if s.get("is_selected"))
        history_cfg = cfg.get("history_selection", {})
        history_score = history_cfg.get("default", 0)
        for t in history_cfg.get("thresholds", []):
            if selected_count >= t.get("min_count", 0):
                history_score = t.get("score", 0)
        if history_score > 0:
            reasons.append(f"入选{selected_count}次")

        # 排名连续上升 (0-5)
        momentum_cfg = cfg.get("momentum", {})
        if len(snapshots) >= momentum_cfg.get("lookback", 3):
            recent = [s.get("rank", 0) for s in snapshots[:3]]
            if recent[0] < recent[1] < recent[2]:
                improvement = recent[2] - recent[0]
                momentum = min(int(improvement * momentum_cfg.get("improvement_per_rank", 0.5)), momentum_cfg.get("max_score", 5))
                if momentum > 0:
                    reasons.append(f"排名上升{improvement}位")
            else:
                momentum = 0
        else:
            momentum = 0

        # 长期稳定 top 20 (0-5)
        top20_count = sum(1 for s in snapshots if s.get("rank", 999) <= 20)
        stab_cfg = cfg.get("stability", {})
        stability_score = stab_cfg.get("default", 0)
        if len(snapshots) > 0:
            stability = top20_count / len(snapshots)
            if stability >= stab_cfg.get("min_stability", 0.8):
                stability_score = stab_cfg.get("high_score", 5)
            elif stability >= stab_cfg.get("mid_stability", 0.6):
                stability_score = stab_cfg.get("mid_score", 3)
            elif stability >= stab_cfg.get("low_stability", 0.4):
                stability_score = stab_cfg.get("low_score", 1)

        total = _clamp(rank_score + history_score + momentum + stability_score, 0, cfg.get("max_total", 35))
        return total, reasons

    # ---- 交易表现 (0-20) ----

    def _trading_perf(self, snapshots: list[dict[str, Any]]) -> tuple[int, list[str]]:
        """交易表现 (0-20)"""
        reasons: list[str] = []
        if not snapshots:
            return 0, reasons

        latest = snapshots[0]
        cfg = self.cfg.get("trading", {})

        # 7d PnL 改善 (0-8)
        pnl_cfg = cfg.get("pnl", {})
        pnl_current = latest.get("pnl_7d", 0)
        if len(snapshots) >= 2:
            pnl_prev = snapshots[1].get("pnl_7d", 0)
            if pnl_prev != 0:
                improvement = (pnl_current - pnl_prev) / abs(pnl_prev) * 100
            else:
                improvement = pnl_current * 10
            pnl_score = pnl_cfg.get("default", 0)
            for t in pnl_cfg.get("improvement_thresholds", []):
                if improvement > t.get("min_pct", 0):
                    pnl_score = t.get("score", 0)
                    break
            if pnl_score > 0:
                reasons.append(f"PnL改善{improvement:.0f}%")
        else:
            pnl_score = pnl_cfg.get("single_snapshot_fallback", 2)

        # 回撤评分 (0-4)
        drawdown = latest.get("max_drawdown", 0)
        d_cfg = cfg.get("drawdown", {})
        if drawdown == 0:
            d_score = d_cfg.get("no_data_score", 2)
        elif drawdown > d_cfg.get("max_drawdown", -10):
            d_score = d_cfg.get("high_score", 4)
        elif drawdown >= d_cfg.get("mid_drawdown", -20):
            d_score = d_cfg.get("mid_score", 3)
        elif drawdown >= d_cfg.get("low_drawdown", -30):
            d_score = d_cfg.get("low_score", 2)
        elif drawdown >= d_cfg.get("min_drawdown", -50):
            d_score = d_cfg.get("min_score", 1)
        else:
            d_score = 0

        # 交易频率稳定性 (0-4)
        trade_count = latest.get("trade_count", 0)
        freq_cfg = cfg.get("trade_frequency", {})
        freq_score = freq_cfg.get("default", 0)
        for t in freq_cfg.get("thresholds", []):
            if trade_count >= t.get("min_trades", 0):
                freq_score = t.get("score", 0)
        if freq_score > 0:
            reasons.append(f"交易{trade_count}次")

        # 胜率评分 (0-6)
        win_rate = latest.get("win_rate", 0)
        wr_score = 0
        for t in cfg.get("win_rate", {}).get("thresholds", []):
            if win_rate >= t.get("min_rate", 0):
                wr_score = t.get("score", 0)
                break
        if wr_score > 0:
            reasons.append(f"胜率{win_rate:.0f}%")

        # 单笔暴赚扣分 (-2 ~ 0)
        penalty_cfg = cfg.get("single_trade_penalty", {})
        penalty = 0
        total_realized_pnl = latest.get("total_realized_pnl", 0) or 0
        holdings_value = latest.get("holdings_value_usd", 0) or 0
        if total_realized_pnl != 0 and holdings_value != 0:
            ratio = abs(holdings_value / total_realized_pnl)
            if ratio < penalty_cfg.get("max_pnl_ratio", 0.5):
                penalty = penalty_cfg.get("penalty", -2)
                reasons.append("单笔仓位集中")

        total = _clamp(pnl_score + d_score + freq_score + wr_score + penalty, 0, cfg.get("max_total", 20))
        return total, reasons

    # ---- 排名趋势 (0-15) ----

    def _rank_trend(self, snapshots: list[dict[str, Any]]) -> tuple[int, list[str]]:
        """排名趋势 (0-15)"""
        reasons: list[str] = []
        if not snapshots:
            return 0, reasons

        latest = snapshots[0]
        current_rank = latest.get("rank", 0)
        cfg = self.cfg.get("rank_trend", {})

        # 1h 排名变化 (0-5)
        if len(snapshots) >= 2:
            prev = snapshots[1].get("rank", 0)
            rank_change_1h = prev - current_rank
        else:
            rank_change_1h = 0

        trend_1h = 0
        for t in cfg.get("change_1h", {}).get("thresholds", []):
            if rank_change_1h >= t.get("min_change", 0):
                trend_1h = t.get("score", 0)
                break
        if trend_1h > 0:
            reasons.append(f"1h↑{rank_change_1h}位")

        # 24h 排名变化 (0-5)
        if len(snapshots) >= 3:
            oldest = snapshots[min(len(snapshots) - 1, 2)].get("rank", 0)
            rank_change_24h = oldest - current_rank
        else:
            rank_change_24h = rank_change_1h

        trend_24h = 0
        for t in cfg.get("change_24h", {}).get("thresholds", []):
            if rank_change_24h >= t.get("min_change", 0):
                trend_24h = t.get("score", 0)
                break
        if trend_24h > 0:
            reasons.append(f"24h↑{rank_change_24h}位")

        # 阈值突破加分 (0-3)
        boost = 0
        if len(snapshots) >= 2:
            prev_rank = snapshots[1].get("rank", 0)
            if prev_rank > 20 and current_rank <= 15:
                boost += cfg.get("threshold_boost", {}).get("cross_20_to_15", 3)
                reasons.append("突破20→15")
            elif prev_rank > 15 and current_rank <= 10:
                boost += cfg.get("threshold_boost", {}).get("cross_15_to_10", 2)
                reasons.append("突破15→10")

        # 跌出 top 10 扣分 (0 to -2)
        top10_drop = 0
        if len(snapshots) >= 2:
            prev_rank = snapshots[1].get("rank", 0)
            if prev_rank <= 10 and current_rank > 10:
                top10_drop = cfg.get("top10_drop_penalty", -2)
                reasons.append("跌出Top10")

        return _clamp(trend_1h + trend_24h + boost + top10_drop, 0, cfg.get("max_total", 15)), reasons

    # ---- Token 市场质量 (0-15) ----

    def _token_market(self, market: dict[str, Any] | None, token_address: str = "") -> tuple[int, list[str]]:
        """Token 市场质量 (0-15)"""
        reasons: list[str] = []
        cfg = self.cfg.get("token_market", {})

        # 有 token 地址即给基础分
        has_token_score = 0
        if token_address:
            has_token_score = cfg.get("has_token", 3)
            reasons.append("有Token")

        if not market:
            return _clamp(has_token_score, 0, cfg.get("max_total", 15)), reasons
        liquidity = market.get("liquidity_usd", 0) or 0
        volume_24h = market.get("volume_24h", 0) or 0
        buy_slippage = market.get("buy_slippage", 0) or 0
        holder_pct = market.get("top_10_holder_pct", 0) or 0

        # 流动性评分 (0-5)
        liq_score = 0
        for t in cfg.get("liquidity", {}).get("thresholds", []):
            if liquidity >= t.get("min_liquidity", 0):
                liq_score = t.get("score", 0)
                break
        if liq_score > 0:
            reasons.append(f"流动性${liquidity:,.0f}")

        # 成交量增长 (0-4)
        vol_score = 0
        for t in cfg.get("volume", {}).get("thresholds", []):
            if volume_24h >= t.get("min_volume", 0):
                vol_score = t.get("score", 0)
                break
        if vol_score > 0:
            reasons.append(f"24h量${volume_24h:,.0f}")

        # 滑点评分 (0-3)
        slip_cfg = cfg.get("slippage", {})
        if buy_slippage == 0:
            slip_score = slip_cfg.get("no_data_score", 1)
        else:
            slip_score = 0
            for t in slip_cfg.get("thresholds", []):
                if buy_slippage < t.get("max_slippage", 0):
                    slip_score = t.get("score", 0)
                    break

        # 持有人分布 (0-3)
        holder_cfg = cfg.get("holder", {})
        if holder_pct == 0:
            holder_score = holder_cfg.get("no_data_score", 1)
        else:
            holder_score = holder_cfg.get("default", 0)
            for t in holder_cfg.get("thresholds", []):
                if holder_pct < t.get("max_pct", 0):
                    holder_score = t.get("score", 0)
                    break

        return _clamp(has_token_score + liq_score + vol_score + slip_score + holder_score, 0, cfg.get("max_total", 15)), reasons

    # ---- 注意力 (0-10) ----

    def _visibility(self, snapshots: list[dict[str, Any]]) -> int:
        """注意力与可见度 (0-10) — 根据排名调整"""
        cfg = self.cfg.get("visibility", {})
        if snapshots:
            rank = snapshots[0].get("rank", 999)
            rank_cfg = cfg.get("rank_based", {})
            if rank <= rank_cfg.get("max_rank", 10):
                return rank_cfg.get("score", 8)
            return cfg.get("low_rank_score", 1)
        return cfg.get("default_score", 3)

    # ---- 风险扣分 (-20 ~ 0) ----

    def _risk_penalty(self, market: dict[str, Any] | None) -> int:
        """风险扣分 (-20 ~ 0)"""
        if not market:
            return 0

        cfg = self.cfg.get("risk_penalty", {})
        penalty = 0
        liquidity = market.get("liquidity_usd", 0) or 0
        price_change = market.get("price_change_24h", 0) or 0
        buy_slippage = market.get("buy_slippage", 0) or 0
        holder_pct = market.get("top_10_holder_pct", 0) or 0
        volume_24h = market.get("volume_24h", 0) or 0

        # 价格暴涨扣分
        for t in cfg.get("price_surge", {}).get("thresholds", []):
            if price_change > t.get("min_change", 0):
                penalty += t.get("penalty", 0)
                break

        # 流动性不足
        for t in cfg.get("low_liquidity", {}).get("thresholds", []):
            if liquidity < t.get("max_liquidity", 0):
                penalty += t.get("penalty", 0)
                break

        # 滑点过高
        for t in cfg.get("high_slippage", {}).get("thresholds", []):
            if buy_slippage > t.get("min_slippage", 0):
                penalty += t.get("penalty", 0)
                break

        # 持有人集中
        for t in cfg.get("holder_concentration", {}).get("thresholds", []):
            if holder_pct > t.get("min_pct", 0):
                penalty += t.get("penalty", 0)
                break

        # 换手率异常
        anomaly_cfg = cfg.get("turnover_anomaly", {})
        if liquidity > 0 and volume_24h / liquidity > anomaly_cfg.get("max_vol_liq_ratio", 5):
            penalty += anomaly_cfg.get("penalty", -3)

        return _clamp(penalty, cfg.get("min_penalty", -20), cfg.get("max_penalty", 0))

    def _risk_reasons(self, market: dict[str, Any] | None) -> list[str]:
        """风险扣分的原因文本"""
        if not market:
            return []
        reasons: list[str] = []
        price_change = market.get("price_change_24h", 0) or 0
        liquidity = market.get("liquidity_usd", 0) or 0
        buy_slippage = market.get("buy_slippage", 0) or 0
        holder_pct = market.get("top_10_holder_pct", 0) or 0

        if price_change > 200:
            reasons.append(f"暴涨{price_change:.0f}%")
        elif price_change > 100:
            reasons.append(f"大涨{price_change:.0f}%")
        if liquidity < 20000:
            reasons.append("流动性极低")
        elif liquidity < 50000:
            reasons.append("流动性偏低")
        if buy_slippage > 3:
            reasons.append("滑点过高")
        if holder_pct > 60:
            reasons.append("筹码集中")

        return reasons

from __future__ import annotations

import re
from typing import Any

from db.models import Agent, AgentSnapshot, Token, TokenMarketSnapshot, utc_now_iso, is_valid_evm_address


ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class DegenClawParser:
    """解析 DegenClaw API 响应 — 参考 SignalHub VirtualsParser 模式"""

    def __init__(self) -> None:
        pass

    def parse_leaderboard(self, raw_items: list[dict[str, Any]]) -> tuple[list[Agent], list[AgentSnapshot]]:
        now = utc_now_iso()
        agents: list[Agent] = []
        snapshots: list[AgentSnapshot] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            agent_id = str(item.get("id") or "")
            name = str(item.get("name") or "")
            if not agent_id or not name:
                continue

            token_address = self._extract_token_address(item)
            token_symbol = str(item.get("token_symbol") or item.get("tokenSymbol", ""))
            rank = int(item.get("rank", 0))

            agent_id_raw = str(item.get("id") or "")
            virtual_id = item.get("virtual_id") or item.get("virtualId")
            profile_url = f"https://degen.virtuals.io/agents/{agent_id_raw}"
            if virtual_id:
                profile_url += f"?vid={virtual_id}"

            agent = Agent(
                agent_id=agent_id,
                name=name,
                profile_url=profile_url,
                token_address=token_address,
                token_symbol=token_symbol,
                chain="base",
                created_at=now,
                updated_at=now,
            )
            agents.append(agent)

            snapshot = AgentSnapshot(
                agent_id=agent_id,
                rank=rank,
                pnl_24h=float(item.get("pnl_24h", 0)),
                pnl_7d=float(item.get("pnl_7d", 0)),
                win_rate=float(item.get("win_rate", 0)),
                max_drawdown=float(item.get("max_drawdown", 0)),
                trade_count=int(item.get("trade_count", 0)),
                is_top_10=bool(item.get("is_top_10", rank <= 10)),
                is_selected=bool(item.get("is_selected", False)),
                last_trade_at=str(item.get("last_trade_at", "")),
                total_realized_pnl=float(item.get("total_realized_pnl", 0)),
                snapshot_at=now,
            )
            snapshots.append(snapshot)

        return agents, snapshots

    def parse_market_data(self, raw: dict[str, Any]) -> TokenMarketSnapshot | None:
        token_address = raw.get("token_address", "")
        if not token_address:
            return None

        return TokenMarketSnapshot(
            token_address=token_address,
            price_usd=float(raw.get("price_usd", 0)),
            liquidity_usd=float(raw.get("liquidity_usd", 0)),
            volume_1h=float(raw.get("volume_1h", 0)),
            volume_24h=float(raw.get("volume_24h", 0)),
            price_change_1h=float(raw.get("price_change_1h", 0)),
            price_change_24h=float(raw.get("price_change_24h", 0)),
            buy_slippage=float(raw.get("buy_slippage", 0)),
            sell_slippage=float(raw.get("sell_slippage", 0)),
            holder_count=int(raw.get("holder_count", 0)),
            top_10_holder_pct=float(raw.get("top_10_holder_pct", 0)),
            snapshot_at=utc_now_iso(),
        )

    def _extract_token_address(self, item: dict[str, Any]) -> str:
        for key in ("token_address", "contract_address", "token"):
            value = item.get(key)
            if isinstance(value, str) and is_valid_evm_address(value):
                return value
        return ""

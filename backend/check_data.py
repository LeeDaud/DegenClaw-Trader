"""检查 pot 数据"""
import sys; sys.path.insert(0, ".")
import json
import httpx

# 1. 检查我们的 API
r = httpx.get("http://127.0.0.1:8002/api/v1/ai-pot/rounds?limit=1", timeout=10)
data = r.json()
round_data = data["data"]["rounds"][0]
print("=== 我们的 API ===")
print(f"Capital: {round_data['total_capital']}")
print(f"Value: {round_data['total_current_value']}")
print(f"Realized: {round_data['total_realized_pnl']}")
print(f"Unrealized: {round_data['total_unrealized_pnl']}")
print(f"Return: {round_data['return_pct']}%")
print()
for sp in round_data.get("sub_pots", []):
    roi = ((sp["current_value"] / sp["starting_capital"]) - 1) * 100 if sp["starting_capital"] else 0
    print(f'{sp["name"]:15s} capital={sp["starting_capital"]:>7.0f} value={sp["current_value"]:>8.2f} realized={sp["realized_pnl"]:>8.2f} unrealized={sp["unrealized_pnl"]:>8.2f} final={sp["final_pnl"]:>8.2f} roi={roi:>6.2f}%')

print()
print("=== 原始 pot-agents API ===")
r2 = httpx.get("https://degen.virtuals.io/api/pot-agents", headers={"user-agent": "Mozilla/5.0"}, timeout=15)
raw = r2.json()
agents = raw.get("data", [])
for a in agents:
    cs = a.get("currentSeason", {})
    name = a.get("name", "?")
    cap = float(cs.get("startingCapital", 0) or 0)
    val = float(cs.get("currentValue", 0) or 0)
    fp = float(cs.get("finalPnl", 0) or 0)
    wallet = cs.get("copyTradeAgentWallet", "")
    print(f'{name:15s} capital={cap:>7.0f} value={val:>8.2f} finalPnl={fp:>8.2f}  wallet={wallet[:30]}...')

print()
print("=== HyperLiquid realtime ===")
for a in agents:
    cs = a.get("currentSeason", {})
    name = a.get("name", "?")
    wallet = cs.get("copyTradeAgentWallet", "")
    if not wallet:
        continue
    try:
        r3 = httpx.post("https://api.hyperliquid.xyz/info", json={"type": "clearinghouseState", "user": wallet}, timeout=10)
        hl = r3.json()
        acct = float(hl["marginSummary"]["accountValue"])
        npos = len(hl.get("assetPositions", []))
        print(f'{name:15s} HL_acctVal={acct:>8.2f} positions={npos}')
    except Exception as e:
        print(f'{name:15s} HL_ERROR: {e}')

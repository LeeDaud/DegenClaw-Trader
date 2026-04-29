import { useQuery } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, RefreshCw, Trophy, Target, Award } from 'lucide-react'

const API_BASE = '/api/v1'

interface PerformanceSummary {
  summary: {
    total_trades: number
    open_positions: number
    win_rate: number
    total_pnl_usdc: number
    avg_pnl_usdc: number
    best_trade: number
    worst_trade: number
  }
  recent_trades: Array<{
    position_id: string
    agent_id: string
    action: string
    entry_price: number
    exit_price: number
    realized_pnl: number
    exit_reason: string
    entered_at: string
    exited_at: string
  }>
  open_positions: Array<{
    position_id: string
    agent_id: string
    entry_price: number
    current_price: number
    unrealized_pnl: number
    cost_usdc: number
    entered_at: string
  }>
}

export default function Performance() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['performance'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/performance/paper`)
      const json = await res.json()
      return json.data as PerformanceSummary
    },
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return <div className="text-center py-20 text-gray-400">Loading...</div>
  }

  if (!data) {
    return <div className="text-center py-20 text-red-400">Failed to load performance data</div>
  }

  const s = data.summary

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Paper Performance</h1>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={isRefetching ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          icon={Trophy}
          label="Total PnL"
          value={`${s.total_pnl_usdc >= 0 ? '+' : ''}$${s.total_pnl_usdc.toFixed(2)}`}
          positive={s.total_pnl_usdc >= 0}
        />
        <SummaryCard
          icon={Target}
          label="Win Rate"
          value={`${s.win_rate}%`}
          positive={s.win_rate >= 50}
        />
        <SummaryCard
          icon={TrendingUp}
          label="Total Trades"
          value={s.total_trades.toString()}
          positive
        />
        <SummaryCard
          icon={TrendingDown}
          label="Open Positions"
          value={s.open_positions.toString()}
          positive={false}
        />
      </div>

      {/* Detailed Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Avg PnL / Trade</div>
          <div className={`text-xl font-bold ${s.avg_pnl_usdc >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {s.avg_pnl_usdc >= 0 ? '+' : ''}${s.avg_pnl_usdc.toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Best Trade</div>
          <div className="text-xl font-bold text-emerald-400">+${s.best_trade.toFixed(2)}</div>
        </div>
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400 uppercase tracking-wider mb-1">Worst Trade</div>
          <div className="text-xl font-bold text-red-400">${s.worst_trade.toFixed(2)}</div>
        </div>
      </div>

      {/* Recent Trades */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Recent Trades</h2>
        {data.recent_trades.length === 0 ? (
          <p className="text-gray-500 text-sm">No trades executed yet.</p>
        ) : (
          <div className="space-y-2">
            {data.recent_trades.map((trade) => {
              const isWin = trade.realized_pnl >= 0
              return (
                <div key={trade.position_id} className="flex items-center justify-between py-2 border-b border-gray-800/50 last:border-0">
                  <div className="flex items-center gap-2">
                    <span className={`p-1 rounded ${isWin ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
                      {isWin ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    </span>
                    <div>
                      <div className="text-sm">
                        <span className="text-gray-400 text-xs">{trade.agent_id.slice(0, 12)}...</span>
                        <span className="text-gray-600 mx-1">·</span>
                        <span className="text-gray-500 text-xs">{trade.exit_reason}</span>
                      </div>
                      <div className="text-xs text-gray-600">
                        Entry ${trade.entry_price.toFixed(6)} → Exit ${trade.exit_price.toFixed(6)}
                      </div>
                    </div>
                  </div>
                  <div className={`text-sm font-mono ${isWin ? 'text-emerald-400' : 'text-red-400'}`}>
                    {isWin ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Open Positions */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Current Open Positions</h2>
        {data.open_positions.length === 0 ? (
          <p className="text-gray-500 text-sm">No open positions.</p>
        ) : (
          <div className="space-y-2">
            {data.open_positions.map((pos) => {
              const pnlPct = pos.entry_price > 0 ? ((pos.current_price - pos.entry_price) / pos.entry_price) * 100 : 0
              return (
                <div key={pos.position_id} className="flex items-center justify-between py-2 border-b border-gray-800/50 last:border-0">
                  <div>
                    <div className="text-sm">
                      <span className="text-gray-400 text-xs">{pos.agent_id.slice(0, 12)}...</span>
                    </div>
                    <div className="text-xs text-gray-600">
                      Entry ${pos.entry_price.toFixed(6)} / Cost ${pos.cost_usdc.toFixed(2)}
                      <span className="ml-2 text-gray-600">{new Date(pos.entered_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                    </div>
                    <div className={`text-xs ${pnlPct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  positive,
}: {
  icon: React.ComponentType<{ size?: number }>
  label: string
  value: string
  positive: boolean
}) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${positive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-gray-500/10 text-gray-400'}`}>
          <Icon size={18} />
        </div>
        <div>
          <div className="text-xs text-gray-400">{label}</div>
          <div className={`text-lg font-bold ${positive ? 'text-emerald-400' : 'text-red-400'}`}>{value}</div>
        </div>
      </div>
    </div>
  )
}

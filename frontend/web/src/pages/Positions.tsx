import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Briefcase, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react'

const API_BASE = '/api/v1'

interface PositionData {
  id: number
  position_id: string
  signal_id: string
  agent_id: string
  agent_name?: string
  token_address: string
  action: string
  entry_price: number
  amount_token: number
  cost_usdc: number
  entry_slippage: number
  entered_at: string
  current_price: number
  unrealized_pnl: number
  exit_price: number
  realized_pnl: number
  exit_slippage: number
  exited_at: string
  exit_reason: string
  stop_loss_pct: number
  take_profit_pct: number
  time_exit_hours: number
  status: string
}

export default function Positions() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['positions'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/positions/paper?limit=100`)
      const json = await res.json()
      return json.data as { positions: PositionData[] }
    },
    refetchInterval: 30_000,
  })

  const positions = data?.positions || []
  const openPositions = positions.filter((p) => p.status === 'open')
  const closedPositions = positions.filter((p) => p.status === 'closed')

  const pnl = (p: PositionData) => p.status === 'closed' ? p.realized_pnl : p.unrealized_pnl

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Paper Positions</h1>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={isRefetching ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400">Open Positions</div>
          <div className="text-2xl font-bold">{openPositions.length}</div>
        </div>
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400">Closed Trades</div>
          <div className="text-2xl font-bold">{closedPositions.length}</div>
        </div>
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <div className="text-xs text-gray-400">Total PnL</div>
          <div className={`text-2xl font-bold ${closedPositions.reduce((s, p) => s + p.realized_pnl, 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            ${closedPositions.reduce((s, p) => s + p.realized_pnl, 0).toFixed(2)}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-gray-400">Loading...</div>
      ) : positions.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <Briefcase size={40} className="mx-auto mb-3 opacity-50" />
          <p>No paper trades yet. Positions appear when trade signals are executed.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Open Positions */}
          {openPositions.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold mb-3">Open Positions ({openPositions.length})</h2>
              <div className="space-y-2">
                {openPositions.map((pos) => (
                  <PositionRow key={pos.position_id} position={pos} />
                ))}
              </div>
            </div>
          )}

          {/* Closed Positions */}
          {closedPositions.length > 0 && (
            <div>
              <h2 className="text-lg font-semibold mb-3">Closed Trades ({closedPositions.length})</h2>
              <div className="space-y-2">
                {closedPositions.map((pos) => (
                  <PositionRow key={pos.position_id} position={pos} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PositionRow({ position: p }: { position: PositionData }) {
  const isClosed = p.status === 'closed'
  const pnlValue = isClosed ? p.realized_pnl : p.unrealized_pnl
  const pnlPct = p.entry_price > 0 ? ((p.current_price - p.entry_price) / p.entry_price) * 100 : 0

  return (
    <div className={`bg-gray-900 rounded-lg border p-4 ${isClosed ? 'border-gray-800' : 'border-emerald-500/30'}`}>
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-lg ${pnlValue >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
          {pnlValue >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm text-gray-500">{p.agent_id.slice(0, 12)}...</span>
            <span className={`text-xs px-2 py-0.5 rounded border ${isClosed ? 'bg-gray-800 border-gray-700 text-gray-400' : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'}`}>
              {p.status}
            </span>
            {p.exit_reason && (
              <span className="text-xs text-gray-500">exit: {p.exit_reason}</span>
            )}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2 text-sm">
            <div>
              <div className="text-xs text-gray-500">Entry</div>
              <div>${p.entry_price.toFixed(6)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Current</div>
              <div>${p.current_price.toFixed(6)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Amount</div>
              <div>{p.amount_token.toFixed(2)} tokens</div>
            </div>
            <div>
              <div className="text-xs text-gray-500">Cost</div>
              <div>${p.cost_usdc.toFixed(2)}</div>
            </div>
          </div>

          <div className="flex items-center gap-4 mt-2 text-sm">
            <div>
              <span className="text-xs text-gray-500">PnL: </span>
              <span className={pnlValue >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                {pnlValue >= 0 ? '+' : ''}${pnlValue.toFixed(2)} ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
              </span>
            </div>
            <div className="text-xs text-gray-500">
              SL {p.stop_loss_pct}% / TP {p.take_profit_pct}%
            </div>
            <div className="text-xs text-gray-500">
              {isClosed
                ? `Closed ${p.exited_at ? new Date(p.exited_at).toLocaleString() : ''}`
                : `Entered ${new Date(p.entered_at).toLocaleString()}`
              }
            </div>
          </div>

          {/* Slippage info */}
          {(p.entry_slippage > 0 || p.exit_slippage > 0) && (
            <div className="text-xs text-gray-600 mt-1">
              Entry slippage: {p.entry_slippage}% {p.exit_slippage > 0 ? `· Exit slippage: ${p.exit_slippage}%` : ''}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

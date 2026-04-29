import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { TrendingUp, TrendingDown, Minus, RefreshCw, Zap, Shield } from 'lucide-react'

const API_BASE = '/api/v1'

interface SignalData {
  id: number
  signal_id: string
  agent_id: string
  agent_name: string
  token_address: string
  action: string
  confidence: string
  reason: string
  key_factors: string
  max_position_usdc: number
  slippage_limit_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  time_exit_hours: number
  risk_checks: string
  window: string
  status: string
  created_at: string
  expires_at: string
}

const actionConfig: Record<string, { icon: React.ComponentType<{ size?: number }>; color: string; label: string }> = {
  probe_buy: { icon: TrendingUp, color: 'text-emerald-400 bg-emerald-500/10', label: 'Probe Buy' },
  confirm_buy: { icon: TrendingUp, color: 'text-emerald-400 bg-emerald-500/10', label: 'Confirm Buy' },
  scale_out: { icon: TrendingDown, color: 'text-yellow-400 bg-yellow-500/10', label: 'Scale Out' },
  exit: { icon: TrendingDown, color: 'text-red-400 bg-red-500/10', label: 'Exit' },
  wait: { icon: Minus, color: 'text-gray-400 bg-gray-500/10', label: 'Wait' },
  watch: { icon: Shield, color: 'text-blue-400 bg-blue-500/10', label: 'Watch' },
}

const confidenceColors: Record<string, string> = {
  high: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  low: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
}

const statusColors: Record<string, string> = {
  active: 'text-emerald-400',
  expired: 'text-gray-500',
  executed: 'text-blue-400',
  cancelled: 'text-red-400',
}

export default function Signals() {
  const { data, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ['signals'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/signals?limit=100`)
      const json = await res.json()
      return json.data as { signals: SignalData[] }
    },
    refetchInterval: 30_000,
  })

  const signals = data?.signals || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trade Signals</h1>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={isRefetching ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-gray-400">Loading...</div>
      ) : signals.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <Zap size={40} className="mx-auto mb-3 opacity-50" />
          <p>No trade signals generated yet. Signal generation runs every 15 minutes.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {signals.map((signal) => {
            const action = actionConfig[signal.action] || actionConfig.watch
            const Icon = action.icon
            return (
              <div key={signal.signal_id} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${action.color}`}>
                    <Icon size={20} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link to={`/agents/${signal.agent_id}`} className="font-semibold hover:text-emerald-400">
                        {signal.agent_name}
                      </Link>
                      <span className="text-xs px-2 py-0.5 rounded border bg-gray-800 border-gray-700 text-gray-300">
                        {action.label}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${confidenceColors[signal.confidence] || confidenceColors.low}`}>
                        {signal.confidence}
                      </span>
                      <span className={`text-xs ${statusColors[signal.status] || 'text-gray-400'}`}>
                        {signal.status}
                      </span>
                    </div>

                    <p className="text-sm text-gray-400 mt-1">{signal.reason}</p>

                    {/* Key metrics */}
                    <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
                      <span>Window: {signal.window}</span>
                      <span>Max pos: ${signal.max_position_usdc.toLocaleString()}</span>
                      <span>SL: {signal.stop_loss_pct}%</span>
                      <span>TP: {signal.take_profit_pct}%</span>
                      <span>Time exit: {signal.time_exit_hours}h</span>
                      {signal.token_address && (
                        <span className="text-gray-600 font-mono">{signal.token_address.slice(0, 10)}...</span>
                      )}
                    </div>

                    {signal.key_factors && signal.key_factors !== '[]' && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {(JSON.parse(signal.key_factors) as string[]).map((f: string, i: number) => (
                          <span key={i} className="text-xs px-2 py-0.5 rounded bg-gray-800 text-gray-400">
                            {f}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="text-xs text-gray-600 mt-2">
                      {new Date(signal.created_at).toLocaleString()}
                      {signal.expires_at && ` · expires ${new Date(signal.expires_at).toLocaleString()}`}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

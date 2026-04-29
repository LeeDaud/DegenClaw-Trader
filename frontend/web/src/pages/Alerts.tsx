import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, TrendingUp, TrendingDown, Zap, RefreshCw, Bell, BellOff } from 'lucide-react'
import { Link } from 'react-router-dom'

const API_BASE = '/api/v1'

interface AlertItem {
  id: number
  alert_id: string
  agent_id: string
  agent_name: string
  alert_type: string
  severity: string
  title: string
  detail: string
  score: number
  notified: number
  created_at: string
}

const alertIcons: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  surge: TrendingUp,
  dump: TrendingDown,
  rank_surge: TrendingUp,
  rank_dump: TrendingDown,
  volume_spike: Zap,
  price_surge: TrendingUp,
  price_dump: TrendingDown,
  combined_surge: TrendingUp,
  combined_dump: TrendingDown,
}

const severityColors: Record<string, string> = {
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
  high: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  medium: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  low: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
}

export default function Alerts() {
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['alerts'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/alerts?limit=50`)
      const json = await res.json()
      return json.data as { alerts: AlertItem[]; unread_count: number }
    },
    refetchInterval: 30_000,
  })

  const scanMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${API_BASE}/alerts/scan`, { method: 'POST' })
      return res.json()
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const alerts = data?.alerts || []
  const unreadCount = data?.unread_count || 0

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">Alerts</h1>
          {unreadCount > 0 && (
            <span className="text-sm bg-red-500/15 text-red-400 px-2.5 py-0.5 rounded-full border border-red-500/30">
              {unreadCount} new
            </span>
          )}
        </div>
        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanMutation.isPending ? 'animate-spin' : ''} />
          Scan
        </button>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-gray-400">Loading...</div>
      ) : alerts.length === 0 ? (
        <div className="text-center py-20 text-gray-500">
          <BellOff size={40} className="mx-auto mb-3 opacity-50" />
          <p>No alerts yet. Click "Scan" to check for signals.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => {
            const Icon = alertIcons[alert.alert_type] || AlertTriangle
            return (
              <div
                key={alert.alert_id}
                className={`bg-gray-900 rounded-lg border p-4 ${alert.notified ? 'border-gray-800' : 'border-emerald-500/30'}`}
              >
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${
                    ['dump', 'rank_dump', 'price_dump', 'combined_dump'].includes(alert.alert_type)
                      ? 'bg-red-500/10 text-red-400'
                      : 'bg-emerald-500/10 text-emerald-400'
                  }`}>
                    {Icon && <Icon size={20} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold">{alert.title}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded border ${severityColors[alert.severity] || severityColors.medium}`}>
                        {alert.severity}
                      </span>
                      <span className="text-xs text-gray-500">score: {alert.score}</span>
                      {!alert.notified && <Bell size={14} className="text-emerald-400 animate-pulse" />}
                    </div>
                    <p className="text-sm text-gray-400 mt-1">{alert.detail}</p>
                    <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                      <Link to={`/agents/${alert.agent_id}`} className="hover:text-emerald-400">
                        {alert.agent_name}
                      </Link>
                      <span>{new Date(alert.created_at).toLocaleString()}</span>
                      <span className="text-gray-600">{alert.alert_type}</span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {scanMutation.isPending && (
        <div className="text-center py-4 text-sm text-gray-400">Scanning for signals...</div>
      )}
      {scanMutation.data && (
        <div className="text-center py-2 text-sm text-emerald-400">
          Scan complete: {scanMutation.data.data?.alerts || 0} alerts, {scanMutation.data.data?.notified || 0} notified
        </div>
      )}
    </div>
  )
}

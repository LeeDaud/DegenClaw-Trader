import { useQuery } from '@tanstack/react-query'
import { fetchDashboard, fetchAgents } from '../api/client'
import { Activity, Users, TrendingUp, AlertTriangle, RefreshCw } from 'lucide-react'

export default function Dashboard() {
  const { data: dashboard, isLoading, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: fetchDashboard,
    refetchInterval: 60_000,
  })

  const { data: agentsData } = useQuery({
    queryKey: ['agents'],
    queryFn: () => fetchAgents(10),
    refetchInterval: 60_000,
  })

  if (isLoading) {
    return <div className="text-center py-20 text-gray-400">Loading...</div>
  }

  if (!dashboard) {
    return <div className="text-center py-20 text-red-400">Failed to load dashboard</div>
  }

  const pot = dashboard.active_pot_round
  const potReturn = pot ? (pot.return_pct ?? pot.pot_pnl) : 0
  const potReturnLabel = pot ? `${potReturn >= 0 ? '+' : ''}${potReturn.toFixed(2)}%` : '-'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors"
        >
          <RefreshCw size={14} />
          Refresh
        </button>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatusCard
          icon={Users}
          label="Agents Tracked"
          value={dashboard.agent_count}
          color="blue"
        />
        <StatusCard
          icon={Activity}
          label="Pot Status"
          value={dashboard.active_pot_round?.status || 'N/A'}
          color="emerald"
        />
        <StatusCard
          icon={TrendingUp}
          label="Pot Return"
          value={potReturnLabel}
          color={potReturn > 0 ? 'emerald' : 'red'}
        />
        <StatusCard
          icon={Users}
          label="Sub-Pots"
          value={pot ? `${pot.active_count ?? '?'}/${pot.sub_pot_count ?? '?'}` : '-'}
          color="blue"
        />
        <StatusCard
          icon={Activity}
          label="Last Collect"
          value={dashboard.last_collect_time ? new Date(dashboard.last_collect_time).toLocaleTimeString() : '-'}
          color="gray"
        />
      </div>

      {/* Polling & Agent Table */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h2 className="text-lg font-semibold mb-3">Agent Leaderboard</h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-400 border-b border-gray-800">
                  <th className="text-left py-2">#</th>
                  <th className="text-left py-2">Agent</th>
                  <th className="text-right py-2">24h PnL</th>
                  <th className="text-right py-2">7d PnL</th>
                  <th className="text-right py-2">Win Rate</th>
                </tr>
              </thead>
              <tbody>
                {topAgents.map((agent) => (
                  <tr key={agent.agent_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="py-2 text-gray-400">{agent.latest_snapshot?.rank || '-'}</td>
                    <td className="py-2 font-medium">{agent.name}</td>
                    <td className={`py-2 text-right ${(agent.latest_snapshot?.pnl_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {agent.latest_snapshot ? `${agent.latest_snapshot.pnl_24h >= 0 ? '+' : ''}${agent.latest_snapshot.pnl_24h}%` : '-'}
                    </td>
                    <td className={`py-2 text-right ${(agent.latest_snapshot?.pnl_7d ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {agent.latest_snapshot ? `${agent.latest_snapshot.pnl_7d >= 0 ? '+' : ''}${agent.latest_snapshot.pnl_7d}%` : '-'}
                    </td>
                    <td className="py-2 text-right text-gray-300">{agent.latest_snapshot?.win_rate ?? '-'}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right panel */}
        <div className="space-y-4">
          {/* Polling Status */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider">Polling</h2>
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Mode</span>
                <span className={dashboard.polling_status.running ? 'text-emerald-400' : 'text-yellow-400'}>
                  {dashboard.polling_status.mode}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Interval</span>
                <span>{dashboard.polling_status.poll_interval_seconds}s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Last Run</span>
                <span>{dashboard.polling_status.last_completed_at ? new Date(dashboard.polling_status.last_completed_at).toLocaleTimeString() : '-'}</span>
              </div>
              {dashboard.polling_status.last_error && (
                <div className="flex items-center gap-1.5 text-red-400 mt-2">
                  <AlertTriangle size={14} />
                  <span className="text-xs">{dashboard.polling_status.last_error}</span>
                </div>
              )}
            </div>
          </div>

          {/* Recent Events */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider">Recent Events</h2>
            <div className="space-y-1.5">
              {dashboard.recent_events.slice(0, 5).map((ev) => (
                <div key={ev.event_id} className="flex items-start gap-2 text-xs">
                  <span className={`mt-0.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                    ev.level === 'error' ? 'bg-red-500' : ev.level === 'warn' ? 'bg-yellow-500' : 'bg-emerald-500'
                  }`} />
                  <div>
                    <span className="text-gray-400">{new Date(ev.created_at).toLocaleTimeString()}</span>{' '}
                    <span className="text-gray-200">{ev.event}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function StatusCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ComponentType<{ size?: number }>
  label: string
  value: string | number
  color: 'blue' | 'emerald' | 'red' | 'gray'
}) {
  const colors = {
    blue: 'text-blue-400 bg-blue-500/10',
    emerald: 'text-emerald-400 bg-emerald-500/10',
    red: 'text-red-400 bg-red-500/10',
    gray: 'text-gray-400 bg-gray-500/10',
  }
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}>
          <Icon size={18} />
        </div>
        <div>
          <div className="text-xs text-gray-400">{label}</div>
          <div className="text-lg font-bold">{value}</div>
        </div>
      </div>
    </div>
  )
}

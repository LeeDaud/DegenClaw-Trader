import { useQuery } from '@tanstack/react-query'
import { fetchDashboard, fetchAgents, fetchCalibrationStatus } from '../api/client'
import { Activity, Users, TrendingUp, AlertTriangle, RefreshCw, BarChart3, Clock } from 'lucide-react'

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

  const { data: calStatus } = useQuery({
    queryKey: ['calibration-status'],
    queryFn: fetchCalibrationStatus,
    refetchInterval: 120_000,
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
  const topAgents = (agentsData?.agents || []).slice(0, 10)

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

          {/* Self-Calibration Status */}
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
              <BarChart3 size={14} />
              Self-Calibration
              <a href="/calibration" className="ml-auto text-[10px] text-gray-500 hover:text-gray-300 transition-colors">Detail →</a>
            </h2>
            {!calStatus ? (
              <div className="text-xs text-gray-500">Loading...</div>
            ) : (
              <div className="space-y-2">
                <CalibrationRow
                  label="A: Outcome Tracking"
                  badge={calStatus.approach_a.stats
                    ? `${calStatus.approach_a.stats.correct}/${calStatus.approach_a.stats.checked} correct`
                    : calStatus.approach_a.pending_evaluations ? `${calStatus.approach_a.pending_evaluations} pending` : 'active'}
                  lastRun={calStatus.approach_a.last_check_at}
                  subline={
                    calStatus.approach_a.hit_rates && Object.keys(calStatus.approach_a.hit_rates).length > 0
                      ? `Surge: ${calStatus.approach_a.hit_rates.surge ?? '-'}% | Dump: ${calStatus.approach_a.hit_rates.dump ?? '-'}%`
                      : undefined
                  }
                />
                <CalibrationRow
                  label="B: Adaptive Thresholds"
                  badge="active"
                  subline="Scale: 0.5x–3.0x"
                />
                <CalibrationRow
                  label="C: Dynamic Window"
                  badge="active"
                  subline="SNR-driven: 4–10 snapshots"
                />
                <CalibrationRow
                  label="D: Full Calibration"
                  badge={calStatus.approach_d.f1_new != null
                    ? `F1 ${calStatus.approach_d.f1_new.toFixed(3)}`
                    : 'pending'}
                  lastRun={calStatus.approach_d.last_run_at}
                  f1Old={calStatus.approach_d.f1_old}
                  f1New={calStatus.approach_d.f1_new}
                />
              </div>
            )}
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

function CalibrationRow({
  label,
  badge,
  lastRun,
  subline,
  f1Old,
  f1New,
}: {
  label: string
  badge?: string
  lastRun?: string | null
  subline?: string
  f1Old?: number | null
  f1New?: number | null
}) {
  const delta = f1Old != null && f1New != null ? ((f1New - f1Old) / f1Old * 100) : null
  return (
    <div className="text-xs border-b border-gray-800/50 last:border-0 pb-1.5 last:pb-0">
      <div className="flex items-center justify-between">
        <span className="text-gray-300">{label}</span>
        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400">
          {badge || 'active'}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-0.5 text-gray-500">
        {lastRun && (
          <span className="flex items-center gap-1">
            <Clock size={10} />
            {new Date(lastRun).toLocaleTimeString()}
          </span>
        )}
        {subline && <span>{subline}</span>}
        {delta != null && (
          <span className={delta >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            F1: {f1Old!.toFixed(3)} → {f1New!.toFixed(3)} ({delta > 0 ? '+' : ''}{delta.toFixed(1)}%)
          </span>
        )}
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

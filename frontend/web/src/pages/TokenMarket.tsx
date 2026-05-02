import { useQuery } from '@tanstack/react-query'
import { fetchCalibrationStatus } from '../api/client'
import { BarChart3, Target, Cpu, Settings, Activity, CheckCircle, Clock, TrendingUp, AlertTriangle, HelpCircle } from 'lucide-react'

export default function TokenMarket() {
  const { data: cal, isLoading } = useQuery({
    queryKey: ['calibration-status'],
    queryFn: fetchCalibrationStatus,
    refetchInterval: 120_000,
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">Loading...</div>
  if (!cal) return <div className="text-center py-20 text-red-400">Failed to load calibration status</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Self-Calibration</h1>
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Activity size={14} />
          <span>Auto-refresh every 2 min</span>
        </div>
      </div>

      {/* 4 approach cards */}
      <div className="grid grid-cols-1 gap-6">
        <ApproachCard
          number="A"
          title={cal.approach_a.name}
          status={cal.approach_a.status}
          description={cal.approach_a.description}
          icon={Target}
          color="blue"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Stats */}
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Outcome Check</h4>
              {cal.approach_a.last_check_at ? (
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Last Run</span>
                    <span>{new Date(cal.approach_a.last_check_at).toLocaleTimeString()}</span>
                  </div>
                  {cal.approach_a.stats && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Checked</span>
                        <span className="text-gray-200">{cal.approach_a.stats.checked}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">
                          <CheckCircle size={12} className="inline text-emerald-400 mr-1" />
                          Correct
                        </span>
                        <span className="text-emerald-400">{cal.approach_a.stats.correct}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">
                          <AlertTriangle size={12} className="inline text-red-400 mr-1" />
                          Wrong
                        </span>
                        <span className="text-red-400">{cal.approach_a.stats.wrong}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-400">Skipped</span>
                        <span className="text-gray-500">{cal.approach_a.stats.skipped}</span>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <div className="text-sm text-gray-500 flex items-center gap-1.5">
                  <Clock size={14} />
                  Awaiting first run
                </div>
              )}
              {cal.approach_a.pending_evaluations != null && cal.approach_a.pending_evaluations > 0 && (
                <div className="mt-2 text-xs text-yellow-400 flex items-center gap-1">
                  <HelpCircle size={12} />
                  {cal.approach_a.pending_evaluations} pending evaluation(s)
                </div>
              )}
            </div>

            {/* Hit rates */}
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Hit Rates (24h)</h4>
              {Object.keys(cal.approach_a.hit_rates || {}).length > 0 ? (
                <div className="space-y-1.5">
                  {Object.entries(cal.approach_a.hit_rates || {}).map(([type, rate]) => (
                    <HitRateBar key={type} type={type} rate={rate} upper={cal.auto_tune.bounds.upper} />
                  ))}
                </div>
              ) : (
                <div className="text-sm text-gray-500">No data yet</div>
              )}
            </div>
          </div>

          {/* Observation windows */}
          {cal.approach_a.windows && (
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-gray-400">
              <span className="text-gray-500 uppercase tracking-wider">Windows:</span>
              {Object.entries(cal.approach_a.windows).map(([type, win]) => (
                <span key={type} className="bg-gray-800 px-2 py-0.5 rounded">{type}: {win}</span>
              ))}
            </div>
          )}
        </ApproachCard>

        <ApproachCard
          number="B"
          title={cal.approach_b.name}
          status={cal.approach_b.status}
          description={cal.approach_b.description}
          icon={Settings}
          color="purple"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Scale Range</h4>
              {cal.approach_b.scale_range ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-3 text-sm">
                    <span className="text-gray-400">Min:</span>
                    <span className="text-emerald-400 font-mono">{cal.approach_b.scale_range.min}</span>
                    <span className="text-gray-600">—</span>
                    <span className="text-gray-400">Max:</span>
                    <span className="text-red-400 font-mono">{cal.approach_b.scale_range.max}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-gray-500">N/A</div>
              )}
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Tracked Metrics</h4>
              <div className="flex flex-wrap gap-1.5">
                {cal.approach_b.metrics?.map((m) => (
                  <span key={m} className="text-xs bg-gray-700 px-2 py-0.5 rounded text-gray-300">{m}</span>
                ))}
              </div>
            </div>
          </div>
        </ApproachCard>

        <ApproachCard
          number="C"
          title={cal.approach_c.name}
          status={cal.approach_c.status}
          description={cal.approach_c.description}
          icon={Cpu}
          color="amber"
        >
          {cal.approach_c.snr_config ? (
            <div className="bg-gray-800/50 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-700 text-xs">
                    <th className="text-left py-2 px-3">SNR</th>
                    <th className="text-center py-2 px-3">Window</th>
                    <th className="text-center py-2 px-3">Consistency</th>
                    <th className="text-left py-2 px-3">Behavior</th>
                  </tr>
                </thead>
                <tbody>
                  {cal.approach_c.snr_config.map((row, i) => (
                    <tr key={i} className="border-b border-gray-800/50 last:border-0">
                      <td className="py-2 px-3 font-mono">{row.snr}</td>
                      <td className="py-2 px-3 text-center font-mono">{row.window}</td>
                      <td className="py-2 px-3 text-center font-mono">{row.consistency}</td>
                      <td className="py-2 px-3 text-gray-300 text-xs">{row.meaning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-sm text-gray-500">Config not available</div>
          )}
        </ApproachCard>

        <ApproachCard
          number="D"
          title={cal.approach_d.name}
          status={cal.approach_d.status}
          description={cal.approach_d.description}
          icon={BarChart3}
          color="emerald"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* F1 comparison */}
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">Last Calibration</h4>
              {cal.approach_d.last_run_at ? (
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Time</span>
                    <span>{new Date(cal.approach_d.last_run_at).toLocaleTimeString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Baseline F1</span>
                    <span className="text-gray-300">{cal.approach_d.f1_old?.toFixed(3) ?? '-'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">New F1</span>
                    <span className={(cal.approach_d.f1_new ?? 0) >= (cal.approach_d.f1_old ?? 0)
                      ? 'text-emerald-400' : 'text-red-400'}>
                      {cal.approach_d.f1_new?.toFixed(3) ?? '-'}
                    </span>
                  </div>
                  {cal.approach_d.f1_old != null && cal.approach_d.f1_new != null && (
                    <div className="flex justify-between pt-1 border-t border-gray-700">
                      <span className="text-gray-400">Improvement</span>
                      <span className={(cal.approach_d.f1_new ?? 0) >= (cal.approach_d.f1_old ?? 0)
                        ? 'text-emerald-400' : 'text-red-400'}>
                        {((cal.approach_d.f1_new - cal.approach_d.f1_old) / cal.approach_d.f1_old * 100).toFixed(1)}%
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-sm text-gray-500 flex items-center gap-1.5">
                  <Clock size={14} />
                  Awaiting first run (scheduled 2:00 AM UTC)
                </div>
              )}
            </div>

            {/* Calibration history */}
            <div className="bg-gray-800/50 rounded-lg p-3">
              <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">History (Last 5)</h4>
              {cal.approach_d.history && cal.approach_d.history.length > 0 ? (
                <div className="space-y-1 text-xs">
                  {cal.approach_d.history.map((h) => (
                    <div key={h.id} className="flex justify-between items-center py-0.5">
                      <span className="text-gray-500">
                        {h.calibrated_at ? new Date(h.calibrated_at).toLocaleDateString() : '-'}
                      </span>
                      <span className="flex gap-2">
                        <span className="text-gray-400">{h.baseline_f1.toFixed(3)}</span>
                        <TrendingUp size={12} className="text-gray-600 self-center" />
                        <span className={h.f1_score >= h.baseline_f1 ? 'text-emerald-400' : 'text-red-400'}>
                          {h.f1_score.toFixed(3)}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-gray-500">No history yet</div>
              )}
            </div>
          </div>
        </ApproachCard>
      </div>

      {/* Auto-tune & Config section at bottom */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Auto-tune */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
            <Activity size={14} />
            Auto-Tune
          </h2>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Last Run</span>
              <span>{cal.auto_tune.last_run_at ? new Date(cal.auto_tune.last_run_at).toLocaleTimeString() : 'Not yet'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Bounds</span>
              <span className="text-gray-300">{cal.auto_tune.bounds.lower}% – {cal.auto_tune.bounds.upper}%</span>
            </div>
            {cal.auto_tune.last_adjustments && cal.auto_tune.last_adjustments.length > 0 && (
              <div>
                <span className="text-gray-400 text-xs">Last adjustments:</span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {cal.auto_tune.last_adjustments.map((adj) => (
                    <span key={adj} className="text-xs bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 rounded">
                      {adj}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Current Config */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
            <Settings size={14} />
            Current Thresholds
          </h2>
          {Object.keys(cal.config).length > 0 ? (
            <div className="text-xs space-y-1">
              {Object.entries(cal.config).map(([key, val]) => (
                <div key={key} className="flex justify-between py-0.5">
                  <span className="text-gray-400">{key}</span>
                  <span className="font-mono text-gray-200">{val}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-gray-500">No config loaded</div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────

function ApproachCard({
  number,
  title,
  status,
  description,
  icon: Icon,
  color,
  children,
}: {
  number: string
  title: string
  status: string
  description?: string | null
  icon: React.ComponentType<{ size?: number; className?: string }>
  color: 'blue' | 'purple' | 'amber' | 'emerald'
  children: React.ReactNode
}) {
  const colors = {
    blue: { border: 'border-blue-500/30', icon: 'text-blue-400', bg: 'bg-blue-500/10' },
    purple: { border: 'border-purple-500/30', icon: 'text-purple-400', bg: 'bg-purple-500/10' },
    amber: { border: 'border-amber-500/30', icon: 'text-amber-400', bg: 'bg-amber-500/10' },
    emerald: { border: 'border-emerald-500/30', icon: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  }
  const c = colors[color]

  return (
    <div className={`bg-gray-900 rounded-lg border ${c.border} p-4`}>
      <div className="flex items-start gap-3 mb-3">
        <div className={`p-2 rounded-lg ${c.bg}`}>
          <Icon size={20} className={c.icon} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold">{number}. {title}</h2>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
              status === 'active' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-yellow-500/10 text-yellow-400'
            }`}>
              {status}
            </span>
          </div>
          {description && <p className="text-xs text-gray-500 mt-0.5">{description}</p>}
        </div>
      </div>
      {children}
    </div>
  )
}

function HitRateBar({ type, rate, upper }: { type: string; rate: number; upper: number }) {
  const pct = Math.min(rate / upper, 1) * 100
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-right text-gray-400 truncate" title={type}>{type}</span>
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            rate >= upper ? 'bg-emerald-500' : rate < 40 ? 'bg-red-500' : 'bg-yellow-500'
          }`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className={`w-10 text-right font-mono ${
        rate >= upper ? 'text-emerald-400' : rate < 40 ? 'text-red-400' : 'text-yellow-400'
      }`}>
        {rate}%
      </span>
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { fetchAgent } from '../api/client'
import type { AgentScoreData } from '../api/client'
import { ArrowLeft, TrendingUp, TrendingDown, Activity, Users, Shield, BarChart3 } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'

const labelColors: Record<string, string> = {
  hot_candidate: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  candidate: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  high_watch: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  watch: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  ignore: 'bg-gray-800 text-gray-600 border-gray-700',
  risk_alert: 'bg-red-500/15 text-red-400 border-red-500/30',
}

const gradeColors: Record<string, string> = {
  A: 'text-emerald-400', B: 'text-blue-400', C: 'text-yellow-400',
  D: 'text-orange-400', E: 'text-red-400', F: 'text-gray-600',
}

const DIMENSIONS = [
  { key: 'council_probability_score', label: 'Council', max: 35 },
  { key: 'trading_performance_score', label: 'Trading', max: 20 },
  { key: 'rank_trend_score', label: 'Rank Trend', max: 15 },
  { key: 'token_market_score', label: 'Token Market', max: 15 },
  { key: 'visibility_score', label: 'Visibility', max: 10 },
]

const dimColors = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ec4899']

function ScoreBreakdown({ score }: { score: AgentScoreData }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-3xl font-bold">{score.score_total}</span>
          <span className={`text-xl font-bold ${gradeColors[score.grade] || ''}`}>/ {score.grade}</span>
        </div>
        <span className={`text-xs px-2.5 py-1 rounded border ${labelColors[score.label] || labelColors.ignore}`}>
          {score.label}
        </span>
      </div>
      <div className="space-y-2">
        {DIMENSIONS.map((dim, i) => {
          const val = (score as any)[dim.key] ?? 0
          const pct = Math.min(val / dim.max, 1)
          return (
            <div key={dim.key}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-400">{dim.label}</span>
                <span className="text-gray-200 font-mono">{val}/{dim.max}</span>
              </div>
              <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{ width: `${pct * 100}%`, backgroundColor: dimColors[i % dimColors.length] }}
                />
              </div>
            </div>
          )
        })}
        {/* Risk penalty as negative bar */}
        <div>
          <div className="flex justify-between text-xs mb-0.5">
            <span className="text-gray-400">Risk Penalty</span>
            <span className="text-red-400 font-mono">{score.risk_penalty}/-20</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-red-500"
              style={{ width: `${Math.min(Math.abs(score.risk_penalty) / 20, 1) * 100}%` }}
            />
          </div>
        </div>
      </div>
      {score.reason && (
        <p className="text-xs text-gray-400 mt-2 italic">{score.reason}</p>
      )}
    </div>
  )
}

export default function AgentDetail() {
  const { agentId } = useParams<{ agentId: string }>()
  const { data, isLoading } = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => fetchAgent(agentId!),
    enabled: !!agentId,
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">Loading...</div>
  if (!data) return <div className="text-center py-20 text-red-400">Agent not found</div>

  const snapshots = (data.snapshots || []).reverse()
  const scores = data.scores || []
  const latestScore = scores[0] || null

  const rankData = snapshots.map((s) => ({
    time: new Date(s.snapshot_at).toLocaleTimeString(),
    rank: s.rank,
  }))

  const scoreTrend = scores.slice().reverse().map((s) => ({
    time: new Date(s.scored_at).toLocaleTimeString(),
    score: s.score_total,
  }))

  const s = data.latest_snapshot
  const m = data.market?.latest

  return (
    <div className="space-y-6">
      <Link to="/agents" className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200">
        <ArrowLeft size={16} />
        Back to Agents
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{data.name}</h1>
            {latestScore && latestScore.label !== 'ignore' && (
              <span className={`text-xs px-2.5 py-0.5 rounded border ${labelColors[latestScore.label] || ''}`}>
                {latestScore.label}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 text-sm text-gray-400">
            <span>ID: {data.agent_id}</span>
            {data.token_address && <span>Token: {data.token_address.slice(0, 10)}...{data.token_address.slice(-6)}</span>}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-gray-400">Rank</div>
            <div className="text-2xl font-bold">#{s?.rank ?? '-'}</div>
          </div>
          <div className="text-right">
            <div className="text-xs text-gray-400">24h PnL</div>
            <div className={`text-xl font-bold ${(s?.pnl_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {s ? `${s.pnl_24h >= 0 ? '+' : ''}$${s.pnl_24h.toLocaleString()}` : '-'}
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatBox icon={BarChart3} label="Score" value={latestScore ? `${latestScore.score_total}` : '-'} color={latestScore && latestScore.score_total >= 60 ? 'emerald' : 'gray'} />
        <StatBox icon={TrendingUp} label="7d PnL" value={s ? `${s.pnl_7d >= 0 ? '+' : ''}${s.pnl_7d}%` : '-'} color={s?.pnl_7d && s.pnl_7d >= 0 ? 'emerald' : 'red'} />
        <StatBox icon={Activity} label="Win Rate" value={s ? `${s.win_rate}%` : '-'} color="blue" />
        <StatBox icon={TrendingDown} label="Max Drawdown" value={s ? `${s.max_drawdown}%` : '-'} color="red" />
        <StatBox icon={Users} label="Trades" value={s?.trade_count ?? '-'} color="gray" />
      </div>

      {/* Score Section */}
      {latestScore && (
        <>
          {/* Score Breakdown + Score Trend */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <Shield size={18} className="text-emerald-400" />
                Score Breakdown
              </h2>
              <ScoreBreakdown score={latestScore} />
            </div>

            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h2 className="text-lg font-semibold mb-3">Score Trend</h2>
              {scoreTrend.length > 1 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={scoreTrend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                    <XAxis dataKey="time" stroke="#6b7280" fontSize={12} />
                    <YAxis domain={[0, 100]} stroke="#6b7280" fontSize={12} />
                    <Tooltip
                      contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#9ca3af' }}
                    />
                    <Line type="monotone" dataKey="score" stroke="#10b981" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="text-center py-10 text-gray-500">Not enough data points</div>
              )}
            </div>
          </div>

          {/* Reason */}
          {latestScore.reason && (
            <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
              <h2 className="text-sm font-semibold mb-2 text-gray-400 uppercase tracking-wider">Analysis</h2>
              <p className="text-sm text-gray-300">{latestScore.reason}</p>
            </div>
          )}
        </>
      )}

      {/* Rank Trend */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h2 className="text-lg font-semibold mb-3">Rank Trend</h2>
        {rankData.length > 1 ? (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={rankData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="time" stroke="#6b7280" fontSize={12} />
              <YAxis reversed stroke="#6b7280" fontSize={12} domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#9ca3af' }}
              />
              <Line type="monotone" dataKey="rank" stroke="#10b981" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-center py-8 text-gray-500">Not enough data points</div>
        )}
      </div>

      {/* Token Market */}
      {m && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h2 className="text-lg font-semibold mb-3">Token Market</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-xs text-gray-400">Price</div>
              <div className="text-lg font-bold">${m.price_usd.toFixed(4)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Liquidity</div>
              <div className="text-lg font-bold">${(m.liquidity_usd / 1000).toFixed(0)}K</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">Volume 24h</div>
              <div className="text-lg font-bold">${(m.volume_24h / 1000).toFixed(0)}K</div>
            </div>
            <div>
              <div className="text-xs text-gray-400">24h Change</div>
              <div className={`text-lg font-bold ${m.price_change_24h >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {m.price_change_24h >= 0 ? '+' : ''}{m.price_change_24h}%
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatBox({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ size?: number }>
  label: string
  value: string | number
  color: 'emerald' | 'red' | 'blue' | 'gray'
}) {
  const colors = { emerald: 'text-emerald-400 bg-emerald-500/10', red: 'text-red-400 bg-red-500/10', blue: 'text-blue-400 bg-blue-500/10', gray: 'text-gray-400 bg-gray-500/10' }
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}><Icon size={18} /></div>
        <div>
          <div className="text-xs text-gray-400">{label}</div>
          <div className="text-lg font-bold">{value}</div>
        </div>
      </div>
    </div>
  )
}

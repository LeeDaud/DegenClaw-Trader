import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchAgents } from '../api/client'
import { Search } from 'lucide-react'
import { useState } from 'react'

const labelColors: Record<string, string> = {
  hot_candidate: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  candidate: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  high_watch: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  watch: 'bg-gray-500/15 text-gray-400 border-gray-500/30',
  ignore: 'bg-gray-800 text-gray-600 border-gray-700',
  risk_alert: 'bg-red-500/15 text-red-400 border-red-500/30',
}

const gradeColors: Record<string, string> = {
  A: 'text-emerald-400',
  B: 'text-blue-400',
  C: 'text-yellow-400',
  D: 'text-orange-400',
  E: 'text-red-400',
  F: 'text-gray-600',
}

export default function AgentList() {
  const [search, setSearch] = useState('')
  const { data, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: () => fetchAgents(50),
    refetchInterval: 60_000,
  })

  const agents = (data?.agents || [])
    .filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const sa = a.latest_score?.score_total ?? 0
      const sb = b.latest_score?.score_total ?? 0
      return sb - sa
    })

  if (isLoading) {
    return <div className="text-center py-20 text-gray-400">Loading...</div>
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agent Leaderboard</h1>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-3 py-1.5 bg-gray-900 border border-gray-800 rounded-md text-sm focus:outline-none focus:border-emerald-500 w-60"
          />
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800 bg-gray-900/50">
              <th className="text-left py-3 px-4">Rank</th>
              <th className="text-left py-3 px-4">Agent</th>
              <th className="text-right py-3 px-4">Score</th>
              <th className="text-center py-3 px-4">Grade</th>
              <th className="text-center py-3 px-4">Label</th>
              <th className="text-right py-3 px-4">24h PnL</th>
              <th className="text-right py-3 px-4">7d PnL</th>
              <th className="text-right py-3 px-4">Win Rate</th>
              <th className="text-right py-3 px-4">Drawdown</th>
              <th className="text-right py-3 px-4">Trades</th>
              <th className="text-center py-3 px-4">Top 10</th>
              <th className="text-center py-3 px-4">AI Pot</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => {
              const s = agent.latest_snapshot
              const sc = agent.latest_score
              return (
                <tr key={agent.agent_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2.5 px-4 text-gray-400 font-mono">{s?.rank || '-'}</td>
                  <td className="py-2.5 px-4">
                    <Link to={`/agents/${agent.agent_id}`} className="font-medium hover:text-emerald-400 transition-colors">
                      {agent.name}
                    </Link>
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono">
                    {sc ? (
                      <span className={sc.score_total >= 60 ? 'text-emerald-400' : sc.score_total >= 40 ? 'text-yellow-400' : 'text-gray-400'}>
                        {sc.score_total}
                      </span>
                    ) : '-'}
                  </td>
                  <td className="py-2.5 px-4 text-center font-mono font-bold">
                    {sc ? <span className={gradeColors[sc.grade] || 'text-gray-400'}>{sc.grade}</span> : '-'}
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    {sc && sc.label !== 'ignore' ? (
                      <span className={`text-xs px-2 py-0.5 rounded border ${labelColors[sc.label] || labelColors.ignore}`}>
                        {sc.label}
                      </span>
                    ) : <span className="text-gray-600">-</span>}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono ${(s?.pnl_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s ? `${s.pnl_24h >= 0 ? '+' : ''}${s.pnl_24h}%` : '-'}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono ${(s?.pnl_7d ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s ? `${s.pnl_7d >= 0 ? '+' : ''}${s.pnl_7d}%` : '-'}
                  </td>
                  <td className="py-2.5 px-4 text-right text-gray-300">{s?.win_rate ?? '-'}%</td>
                  <td className="py-2.5 px-4 text-right text-red-400">{s?.max_drawdown ?? '-'}%</td>
                  <td className="py-2.5 px-4 text-right text-gray-300">{s?.trade_count ?? '-'}</td>
                  <td className="py-2.5 px-4 text-center">
                    {s?.is_top_10 ? <span className="text-emerald-400">●</span> : <span className="text-gray-600">○</span>}
                  </td>
                  <td className="py-2.5 px-4 text-center">
                    {s?.is_selected ? <span className="text-emerald-400">●</span> : <span className="text-gray-600">○</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

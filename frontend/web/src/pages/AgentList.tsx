import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { fetchAgents } from '../api/client'
import { Search, ExternalLink, TrendingUp } from 'lucide-react'
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
    queryFn: () => fetchAgents(200),
    refetchInterval: 60_000,
  })

  const agents = (data?.agents || [])
    .filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      const ra = a.latest_snapshot?.rank ?? 9999
      const rb = b.latest_snapshot?.rank ?? 9999
      return ra - rb
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
              <th className="text-left py-3 px-4">#</th>
              <th className="text-left py-3 px-4">Agent</th>
              <th className="text-left py-3 px-4">Token</th>
              <th className="text-right py-3 px-4">Score</th>
              <th className="text-center py-3 px-4">Grade</th>
              <th className="text-center py-3 px-4">Label</th>
              <th className="text-right py-3 px-4">24h PnL</th>
              <th className="text-right py-3 px-4">7d PnL</th>
              <th className="text-right py-3 px-4">Win Rate</th>
              <th className="text-right py-3 px-4">Trades</th>
              <th className="text-center py-3 px-4">Trend</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => {
              const s = agent.latest_snapshot
              const sc = agent.latest_score
              const isTop10 = (s?.rank ?? 999) <= 10
              // Rank change: negative means rank improved (lower number = better)
              return (
                <tr key={agent.agent_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2.5 px-4">
                    <span className={`font-mono ${isTop10 ? 'text-emerald-400 font-bold' : 'text-gray-400'}`}>
                      {s?.rank || '-'}
                    </span>
                  </td>
                  <td className="py-2.5 px-4">
                    <div className="flex items-center gap-2">
                      <Link to={`/agents/${agent.agent_id}`} className="font-medium hover:text-emerald-400 transition-colors">
                        {agent.name}
                      </Link>
                      <a
                        href={agent.profile_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-gray-500 hover:text-emerald-400 transition-colors"
                        title="View on DegenClaw"
                      >
                        <ExternalLink size={14} />
                      </a>
                    </div>
                  </td>
                  <td className="py-2.5 px-4">
                    <span className="font-mono text-xs text-gray-400">
                      {agent.token_symbol || (agent.token_address ? `${agent.token_address.slice(0, 6)}...` : '-')}
                    </span>
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
                    {s ? `${s.pnl_24h >= 0 ? '+' : ''}$${s.pnl_24h.toLocaleString()}` : '-'}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono ${(s?.pnl_7d ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {s ? `${s.pnl_7d >= 0 ? '+' : ''}${s.pnl_7d}%` : '-'}
                  </td>
                  <td className="py-2.5 px-4 text-right text-gray-300">{s?.win_rate ?? '-'}%</td>
                  <td className="py-2.5 px-4 text-right text-gray-300">{s?.trade_count ?? '-'}</td>
                  <td className="py-2.5 px-4 text-center">
                    {isTop10 ? (
                      <span className="inline-flex items-center gap-1 text-emerald-400 text-xs">
                        <TrendingUp size={14} /> Top 10
                      </span>
                    ) : (
                      <span className="text-gray-600 text-xs">-</span>
                    )}
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

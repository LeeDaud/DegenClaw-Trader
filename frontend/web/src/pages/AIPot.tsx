import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchAIPotRounds, fetchAIPotCouncil, fetchAIPotRaw, triggerScan, type AIPotRound, type CouncilEvaluation } from '../api/client'
import { RefreshCw } from 'lucide-react'
import { useState } from 'react'

const tabs = ['Summary', 'Sub-Pots', 'Council', 'Raw Data']

export default function AIPot() {
  const [tab, setTab] = useState(0)
  const queryClient = useQueryClient()

  const scanMutation = useMutation({
    mutationFn: triggerScan,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-pot-rounds'] })
      queryClient.invalidateQueries({ queryKey: ['ai-pot-council'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const roundsQuery = useQuery({
    queryKey: ['ai-pot-rounds'],
    queryFn: () => fetchAIPotRounds(5),
    refetchInterval: 60_000,
  })
  const councilQuery = useQuery({
    queryKey: ['ai-pot-council'],
    queryFn: () => fetchAIPotCouncil(5),
    refetchInterval: 60_000,
  })
  const rawQuery = useQuery({
    queryKey: ['ai-pot-raw'],
    queryFn: () => fetchAIPotRaw(),
    refetchInterval: 120_000,
  })

  const rounds = roundsQuery.data?.rounds || []
  const evaluations = councilQuery.data?.evaluations || []
  const latestRound = rounds[0]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">AI Pot</h1>
        <button
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-gray-800 rounded-md hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={scanMutation.isPending ? 'animate-spin' : ''} />
          {scanMutation.isPending ? 'Scanning...' : 'Refresh Data'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800">
        {tabs.map((label, i) => (
          <button
            key={label}
            onClick={() => setTab(i)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-[1px] ${
              tab === i
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab: Summary */}
      {tab === 0 && (
        <div className="grid grid-cols-4 gap-4">
          {rounds.length === 0 ? (
            <div className="col-span-4 text-center py-20 text-gray-500">No pot data available</div>
          ) : (
            <>
              <SummaryCard label="Total Capital" value={formatUSD(latestRound.total_capital)} />
              <SummaryCard label="Current Value" value={formatUSD(latestRound.total_current_value)} />
              <SummaryCard label="Total PnL" value={formatUSD(latestRound.pot_pnl)} cn={latestRound.pot_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'} />
              <SummaryCard label="Return" value={`${latestRound.return_pct >= 0 ? '+' : ''}${latestRound.return_pct}%`} cn={latestRound.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'} />
              <SummaryCard label="Sub-Pots" value={String(latestRound.sub_pots?.length || 0)} cn="text-blue-400" />
              <SummaryCard label="Status" value={latestRound.status} cn="text-yellow-400" />
              <SummaryCard label="Season" value={latestRound.season_name || latestRound.season_id || '-'} />
              <SummaryCard label="Realized PnL" value={formatUSD(latestRound.total_realized_pnl)} cn={latestRound.total_realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'} />
            </>
          )}
        </div>
      )}

      {/* Tab: Sub-Pots */}
      {tab === 1 && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
          {rounds.map((round) => (
            <div key={round.round_id} className="p-4 border-b border-gray-800 last:border-b-0">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold text-emerald-400">{round.season_name || round.round_id}</h3>
                <span className={`text-xs px-2 py-0.5 rounded ${round.status === 'active' ? 'bg-green-500/10 text-green-400' : 'bg-gray-800 text-gray-400'}`}>
                  {round.status}
                </span>
              </div>
              <SubPotsTable subPots={round.sub_pots || []} />
            </div>
          ))}
          {rounds.length === 0 && <div className="text-center py-20 text-gray-500">No sub-pots data</div>}
        </div>
      )}

      {/* Tab: Council */}
      {tab === 2 && (
        <div className="space-y-4">
          {evaluations.length === 0 ? (
            <div className="text-center py-20 text-gray-500">No council evaluations available</div>
          ) : (
            evaluations.map((ev) => (
              <CouncilPanel key={ev.id} evaluation={ev} />
            ))
          )}
        </div>
      )}

      {/* Tab: Raw Data */}
      {tab === 3 && (
        <div className="space-y-4">
          {rawQuery.isLoading ? (
            <div className="text-center py-20 text-gray-500">Loading...</div>
          ) : (
            <>
              <RawBlock title="Pot Agents (API)" data={rawQuery.data?.pot_agents} />
              <RawBlock title="Council (API)" data={rawQuery.data?.council} />

              {/* Stored evaluations: Model Verdicts + Raw Data */}
              {evaluations.map((ev) => {
                let mv: any = null
                try { mv = JSON.parse(ev.model_verdicts) } catch { /* ignore */ }
                let rd: any = null
                try { rd = JSON.parse(ev.raw_data) } catch { /* ignore */ }
                return (
                  <div key={ev.id} className="space-y-2">
                    {mv && <RawBlock title={`Model Verdicts (Season ${ev.season_name || ev.season_id})`} data={mv} />}
                    {rd && <RawBlock title={`Council Raw Data (Season ${ev.season_name || ev.season_id})`} data={rd} />}
                  </div>
                )
              })}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/* --- Sub-components --- */

function SummaryCard({ label, value, cn = '' }: { label: string; value: string; cn?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="text-xs text-gray-400 mb-1">{label}</div>
      <div className={`text-lg font-bold font-mono ${cn || 'text-gray-100'}`}>{value}</div>
    </div>
  )
}

function SubPotsTable({ subPots }: { subPots: AIPotRound['sub_pots'] }) {
  if (!subPots || subPots.length === 0) return <div className="text-gray-500 text-sm py-4 text-center">No sub-pots</div>
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-gray-400 border-b border-gray-800">
          <th className="text-left py-2 px-2">#</th>
          <th className="text-left py-2 px-2">Name</th>
          <th className="text-left py-2 px-2">Agent</th>
          <th className="text-left py-2 px-2">Token</th>
          <th className="text-right py-2 px-2">Capital</th>
          <th className="text-right py-2 px-2">Value</th>
          <th className="text-right py-2 px-2">Realized</th>
          <th className="text-right py-2 px-2">Unrealized</th>
          <th className="text-right py-2 px-2">Total PnL</th>
          <th className="text-right py-2 px-2">ROI</th>
          <th className="text-center py-2 px-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {subPots.map((sp, i) => {
          const roi = sp.starting_capital > 0 ? ((sp.current_value / sp.starting_capital) - 1) * 100 : 0
          return (
            <tr key={sp.sub_pot_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
              <td className="py-2 px-2 font-mono text-gray-400">{i + 1}</td>
              <td className="py-2 px-2 font-medium">{sp.name}</td>
              <td className="py-2 px-2 text-gray-300">{sp.agent_name}</td>
              <td className="py-2 px-2 font-mono text-gray-400">{sp.token_symbol || '-'}</td>
              <td className="py-2 px-2 text-right font-mono">{formatUSD(sp.starting_capital)}</td>
              <td className="py-2 px-2 text-right font-mono">{formatUSD(sp.current_value)}</td>
              <td className={`py-2 px-2 text-right font-mono ${sp.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatUSD(sp.realized_pnl)}</td>
              <td className={`py-2 px-2 text-right font-mono ${sp.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatUSD(sp.unrealized_pnl)}</td>
              <td className={`py-2 px-2 text-right font-mono font-bold ${sp.final_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatUSD(sp.final_pnl)}</td>
              <td className={`py-2 px-2 text-right font-mono ${roi >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{roi >= 0 ? '+' : ''}{roi.toFixed(2)}%</td>
              <td className="py-2 px-2 text-center">
                <span className={`px-1.5 py-0.5 rounded text-xs ${sp.status === 'ACTIVE' ? 'bg-green-500/10 text-green-400' : 'bg-gray-800 text-gray-400'}`}>
                  {sp.status}
                </span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function CouncilPanel({ evaluation }: { evaluation: CouncilEvaluation }) {
  const agentScores = evaluation.agent_scores || []
  let consensusAgents: string[] = []
  try { consensusAgents = JSON.parse(evaluation.consensus_agents) } catch { /* ignore */ }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-purple-400">Season {evaluation.season_name || evaluation.season_id}</h3>
        <span className="text-xs text-gray-400">{evaluation.total_agents_analyzed} agents analyzed</span>
      </div>

      {/* Consensus Agents */}
      {consensusAgents.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-2">Consensus Agents</div>
          <div className="flex flex-wrap gap-2">
            {consensusAgents.map((name) => (
              <span key={name} className="text-xs px-2 py-1 bg-purple-500/10 text-purple-400 border border-purple-500/30 rounded">{name}</span>
            ))}
          </div>
        </div>
      )}

      {/* Final Top 10 Table */}
      {agentScores.length > 0 && (
        <div>
          <div className="text-xs text-gray-400 mb-2">Final Top 10</div>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 border-b border-gray-800">
                <th className="text-left py-2 px-2">Rank</th>
                <th className="text-left py-2 px-2">Agent</th>
                <th className="text-right py-2 px-2">Votes</th>
                <th className="text-left py-2 px-2">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {agentScores.map((as) => (
                <tr key={`${as.agent_name}-${as.rank}`} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2 px-2 font-mono text-purple-400">#{as.rank}</td>
                  <td className="py-2 px-2 font-medium">{as.agent_name}</td>
                  <td className="py-2 px-2 text-right font-mono">{as.votes}</td>
                  <td className="py-2 px-2 max-w-md">
                    <RationalePopover rationale={as.per_model_rationale} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function RationalePopover({ rationale }: { rationale: string }) {
  let parsed: Record<string, string> = {}
  try { parsed = JSON.parse(rationale) } catch { /* ignore */ }
  const entries = Object.entries(parsed)
  if (entries.length === 0) return <span className="text-gray-500">-</span>

  return (
    <div className="group relative">
      <span className="text-purple-400 cursor-help underline decoration-dotted">{entries.length} models</span>
      <div className="absolute left-0 bottom-full mb-2 w-72 bg-gray-950 border border-gray-700 rounded-lg p-3 shadow-xl hidden group-hover:block z-10">
        {entries.map(([model, reason]) => (
          <div key={model} className="mb-2 last:mb-0">
            <div className="text-purple-400 font-medium text-xs">{model}</div>
            <div className="text-gray-300 text-xs mt-0.5">{String(reason).slice(0, 200)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function RawBlock({ title, data }: { title: string; data: unknown }) {
  return (
    <details className="bg-gray-900 border border-gray-800 rounded-lg">
      <summary className="px-4 py-3 cursor-pointer text-sm font-medium text-gray-300 hover:text-gray-100">{title}</summary>
      <pre className="px-4 pb-4 text-xs text-gray-300 max-h-96 overflow-y-auto">
        {data ? JSON.stringify(data, null, 2) : 'null'}
      </pre>
    </details>
  )
}

function formatUSD(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toFixed(2)
}

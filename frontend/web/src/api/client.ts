const API_BASE = '/api/v1'

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  const json = await res.json()
  if (!json.success) throw new Error(json.error?.message || 'API error')
  return json.data as T
}

export interface AgentScoreData {
  id: number
  agent_id: string
  token_address: string
  score_total: number
  council_probability_score: number
  trading_performance_score: number
  rank_trend_score: number
  token_market_score: number
  visibility_score: number
  risk_penalty: number
  grade: string
  label: string
  reason: string
  scored_at: string
}

export interface Agent {
  id: number
  agent_id: string
  name: string
  profile_url: string
  token_address: string
  chain: string
  created_at: string
  updated_at: string
  latest_snapshot: AgentSnapshot | null
  latest_market: MarketSnapshot | null
  latest_score: AgentScoreData | null
}

export interface AgentSnapshot {
  id: number
  agent_id: string
  rank: number
  pnl_24h: number
  pnl_7d: number
  win_rate: number
  max_drawdown: number
  trade_count: number
  is_top_10: number
  is_selected: number
  snapshot_at: string
}

export interface MarketSnapshot {
  id: number
  token_address: string
  price_usd: number
  liquidity_usd: number
  volume_1h: number
  volume_24h: number
  price_change_1h: number
  price_change_24h: number
  buy_slippage: number
  sell_slippage: number
  holder_count: number
  top_10_holder_pct: number
  snapshot_at: string
}

export interface Token {
  id: number
  token_address: string
  symbol: string
  name: string
  pool_address: string
  chain: string
  latest_market: MarketSnapshot | null
}

export interface SystemEvent {
  id: number
  event_id: string
  module: string
  level: string
  event: string
  detail: string
  trace_id: string
  created_at: string
}

export interface DashboardSummary {
  agent_count: number
  last_collect_time: string | null
  active_pot_round: {
    round_id: string
    status: string
    selected_agents: string
    pot_pnl: number
  } | null
  recent_events: SystemEvent[]
  top_movers: Array<{
    agent_id: string
    name: string
    rank_change: number
    rank: number
    prev_rank: number
  }>
  polling_status: {
    mode: string
    running: boolean
    is_scanning: boolean
    poll_interval_seconds: number
    last_completed_at: string | null
    last_error: string | null
  }
}

export async function fetchAgents(limit = 50, offset = 0) {
  return apiGet<{ agents: Agent[]; total: number }>(`/agents?limit=${limit}&offset=${offset}`)
}

export async function fetchAgent(agentId: string) {
  return apiGet<Agent & { snapshots: AgentSnapshot[]; market: { latest: MarketSnapshot | null; history: MarketSnapshot[] } | null; scores: AgentScoreData[] }>(`/agents/${agentId}`)
}

export async function fetchTokens(limit = 50) {
  return apiGet<{ tokens: Token[] }>(`/tokens?limit=${limit}`)
}

export async function fetchToken(address: string) {
  return apiGet<Token & { latest_market: MarketSnapshot | null; history: MarketSnapshot[] }>(`/tokens/${address}`)
}

export async function fetchDashboard() {
  return apiGet<DashboardSummary>('/dashboard')
}

export async function fetchEvents(limit = 50, module?: string, level?: string) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (module) params.set('module', module)
  if (level) params.set('level', level)
  return apiGet<{ events: SystemEvent[] }>(`/events?${params}`)
}

export async function fetchScores(limit = 50) {
  return apiGet<{ scores: AgentScoreData[] }>(`/scores?limit=${limit}`)
}

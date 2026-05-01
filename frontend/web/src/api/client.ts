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

export interface CouncilLeaderboardScore {
  agent_id: string
  season_id: string
  council_rank: number
  council_score: number
  council_votes: number
  fetched_at: string
}

export interface Agent {
  id: number
  agent_id: string
  name: string
  profile_url: string
  token_address: string
  token_symbol: string
  chain: string
  created_at: string
  updated_at: string
  latest_snapshot: AgentSnapshot | null
  latest_market: MarketSnapshot | null
  latest_score: AgentScoreData | null
  council_score: CouncilLeaderboardScore | null
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

export interface TradeSignalData {
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

export interface PaperPositionData {
  id: number
  position_id: string
  signal_id: string
  agent_id: string
  token_address: string
  action: string
  entry_price: number
  amount_token: number
  cost_usdc: number
  entry_slippage: number
  entered_at: string
  current_price: number
  unrealized_pnl: number
  exit_price: number
  realized_pnl: number
  exit_slippage: number
  exited_at: string
  exit_reason: string
  stop_loss_pct: number
  take_profit_pct: number
  time_exit_hours: number
  status: string
}

export interface PaperPerformance {
  summary: {
    total_trades: number
    open_positions: number
    win_rate: number
    total_pnl_usdc: number
    avg_pnl_usdc: number
    best_trade: number
    worst_trade: number
  }
  recent_trades: PaperPositionData[]
  open_positions: PaperPositionData[]
}

export async function fetchSignals(limit = 50, status?: string) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  return apiGet<{ signals: TradeSignalData[] }>(`/signals?${params}`)
}

export async function fetchPositions(limit = 50, status?: string) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  return apiGet<{ positions: PaperPositionData[] }>(`/positions/paper?${params}`)
}

export async function fetchPerformance() {
  return apiGet<PaperPerformance>('/performance/paper')
}

// --- AI Pot ---

export interface AIPotSubAgent {
  round_id: string
  sub_pot_id: string
  name: string
  status: string
  agent_id: string
  agent_name: string
  token_address: string
  token_symbol: string
  starting_capital: number
  current_value: number
  realized_pnl: number
  unrealized_pnl: number
  final_pnl: number
  positions: string
  snapshot_at: string
}

export interface AIPotRound {
  round_id: string
  round_start: string
  round_end: string
  status: string
  selected_agents: string
  pot_pnl: number
  season_id: string
  season_name: string
  total_capital: number
  total_current_value: number
  total_realized_pnl: number
  total_unrealized_pnl: number
  return_pct: number
  raw_data: string
  created_at: string
  updated_at: string
  sub_pots?: AIPotSubAgent[]
}

export interface CouncilAgentScore {
  season_id: string
  evaluation_id: number
  agent_name: string
  rank: number
  votes: number
  per_model_rationale: string
  created_at: string
}

export interface CouncilEvaluation {
  id: number
  season_id: string
  season_name: string
  pot_size: number
  total_agents_analyzed: number
  consensus_agents: string
  model_verdicts: string
  raw_data: string
  fetched_at: string
  agent_scores?: CouncilAgentScore[]
}

export interface PotPnlSnapshot {
  sub_pot_id: string
  round_id: string
  current_value: number
  realized_pnl: number
  unrealized_pnl: number
  final_pnl: number
  snapshot_at: string
}

export async function fetchAIPotRounds(limit = 20) {
  return apiGet<{ rounds: AIPotRound[] }>(`/ai-pot/rounds?limit=${limit}`)
}

export async function fetchAIPotCouncil(limit = 10) {
  return apiGet<{ evaluations: CouncilEvaluation[] }>(`/ai-pot/council?limit=${limit}`)
}

export async function fetchSubPotPnlHistory(subPotId: string, limit = 50) {
  return apiGet<{ sub_pot_id: string; snapshots: PotPnlSnapshot[]; sub_agent: AIPotSubAgent | null }>(`/ai-pot/sub-pots/${subPotId}/pnl-history?limit=${limit}`)
}

export async function fetchAIPotRaw() {
  return apiGet<{ pot_agents: unknown[]; council: unknown }>('/ai-pot/raw')
}

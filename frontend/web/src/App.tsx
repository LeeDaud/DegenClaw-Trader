import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import AgentList from './pages/AgentList'
import AgentDetail from './pages/AgentDetail'
import TokenMarket from './pages/TokenMarket'
import Alerts from './pages/Alerts'
import Signals from './pages/Signals'
import Positions from './pages/Positions'
import Performance from './pages/Performance'
import SystemLogs from './pages/SystemLogs'
import AIPot from './pages/AIPot'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<AgentList />} />
        <Route path="/agents/:agentId" element={<AgentDetail />} />
        <Route path="/calibration" element={<TokenMarket />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/logs" element={<SystemLogs />} />
        <Route path="/ai-pot" element={<AIPot />} />
      </Routes>
    </Layout>
  )
}

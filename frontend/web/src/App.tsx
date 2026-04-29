import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import AgentList from './pages/AgentList'
import AgentDetail from './pages/AgentDetail'
import TokenMarket from './pages/TokenMarket'
import Alerts from './pages/Alerts'
import SystemLogs from './pages/SystemLogs'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<AgentList />} />
        <Route path="/agents/:agentId" element={<AgentDetail />} />
        <Route path="/tokens" element={<TokenMarket />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/logs" element={<SystemLogs />} />
      </Routes>
    </Layout>
  )
}

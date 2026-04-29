import { useQuery } from '@tanstack/react-query'
import { fetchEvents } from '../api/client'
import { AlertCircle, Info, AlertTriangle } from 'lucide-react'
import { useState } from 'react'

const levelIcons = {
  info: Info,
  warn: AlertTriangle,
  error: AlertCircle,
  fatal: AlertCircle,
}

const levelColors: Record<string, string> = {
  info: 'text-blue-400 bg-blue-500/10',
  warn: 'text-yellow-400 bg-yellow-500/10',
  error: 'text-red-400 bg-red-500/10',
  fatal: 'text-red-400 bg-red-500/10',
}

export default function SystemLogs() {
  const [moduleFilter, setModuleFilter] = useState<string>('')
  const [levelFilter, setLevelFilter] = useState<string>('')

  const { data, isLoading } = useQuery({
    queryKey: ['events', moduleFilter, levelFilter],
    queryFn: () => fetchEvents(100, moduleFilter || undefined, levelFilter || undefined),
    refetchInterval: 30_000,
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">Loading...</div>

  const events = data?.events || []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">System Logs</h1>
        <div className="flex gap-2">
          <select
            value={moduleFilter}
            onChange={(e) => setModuleFilter(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-md px-3 py-1.5 text-sm"
          >
            <option value="">All Modules</option>
            <option value="collector">Collector</option>
            <option value="system">System</option>
            <option value="api">API</option>
          </select>
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            className="bg-gray-900 border border-gray-800 rounded-md px-3 py-1.5 text-sm"
          >
            <option value="">All Levels</option>
            <option value="info">Info</option>
            <option value="warn">Warn</option>
            <option value="error">Error</option>
          </select>
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800 bg-gray-900/50">
              <th className="text-left py-3 px-4">Time</th>
              <th className="text-left py-3 px-4">Module</th>
              <th className="text-left py-3 px-4">Level</th>
              <th className="text-left py-3 px-4">Event</th>
              <th className="text-left py-3 px-4">Detail</th>
            </tr>
          </thead>
          <tbody>
            {events.map((ev) => {
              const LevelIcon = levelIcons[ev.level as keyof typeof levelIcons] || Info
              return (
                <tr key={ev.event_id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2 px-4 text-gray-400 whitespace-nowrap font-mono text-xs">
                    {new Date(ev.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 px-4">
                    <span className="text-xs bg-gray-800 px-2 py-0.5 rounded">{ev.module}</span>
                  </td>
                  <td className="py-2 px-4">
                    <div className={`flex items-center gap-1.5 text-xs px-2 py-0.5 rounded w-fit ${levelColors[ev.level] || 'text-gray-400'}`}>
                      <LevelIcon size={12} />
                      {ev.level}
                    </div>
                  </td>
                  <td className="py-2 px-4 font-medium">{ev.event}</td>
                  <td className="py-2 px-4 text-gray-400 max-w-md truncate">{ev.detail}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {events.length === 0 && (
          <div className="text-center py-10 text-gray-500">No events found</div>
        )}
      </div>
    </div>
  )
}

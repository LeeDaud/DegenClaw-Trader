import { useQuery } from '@tanstack/react-query'
import { fetchTokens } from '../api/client'

export default function TokenMarket() {
  const { data, isLoading } = useQuery({
    queryKey: ['tokens'],
    queryFn: () => fetchTokens(50),
    refetchInterval: 60_000,
  })

  if (isLoading) return <div className="text-center py-20 text-gray-400">Loading...</div>

  const tokens = data?.tokens || []

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Token Market</h1>

      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800 bg-gray-900/50">
              <th className="text-left py-3 px-4">Token</th>
              <th className="text-right py-3 px-4">Price</th>
              <th className="text-right py-3 px-4">Liquidity</th>
              <th className="text-right py-3 px-4">Vol 24h</th>
              <th className="text-right py-3 px-4">1h Change</th>
              <th className="text-right py-3 px-4">24h Change</th>
              <th className="text-right py-3 px-4">Buy Slippage</th>
              <th className="text-right py-3 px-4">Holders</th>
              <th className="text-center py-3 px-4">Chain</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((token) => {
              const m = token.latest_market
              return (
                <tr key={token.token_address} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2.5 px-4">
                    <div className="font-medium">{token.symbol || token.token_address.slice(0, 10)}</div>
                    {token.symbol && <div className="text-xs text-gray-500">{token.token_address.slice(0, 10)}...</div>}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono">${m?.price_usd?.toFixed(4) ?? '-'}</td>
                  <td className="py-2.5 px-4 text-right font-mono">{m ? `$${(m.liquidity_usd / 1000).toFixed(0)}K` : '-'}</td>
                  <td className="py-2.5 px-4 text-right font-mono">{m ? `$${(m.volume_24h / 1000).toFixed(0)}K` : '-'}</td>
                  <td className={`py-2.5 px-4 text-right font-mono ${(m?.price_change_1h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {m ? `${m.price_change_1h >= 0 ? '+' : ''}${m.price_change_1h}%` : '-'}
                  </td>
                  <td className={`py-2.5 px-4 text-right font-mono ${(m?.price_change_24h ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {m ? `${m.price_change_24h >= 0 ? '+' : ''}${m.price_change_24h}%` : '-'}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-gray-300">{m ? `${m.buy_slippage}%` : '-'}</td>
                  <td className="py-2.5 px-4 text-right font-mono text-gray-300">{m?.holder_count ?? '-'}</td>
                  <td className="py-2.5 px-4 text-center">
                    <span className="text-xs bg-gray-800 px-2 py-0.5 rounded">{token.chain}</span>
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

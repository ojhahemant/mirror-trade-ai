import { TrendingUp, TrendingDown, Wifi, WifiOff } from 'lucide-react'
import { useStore } from '../store/index.js'
import clsx from 'clsx'

export default function LivePriceBadge({ compact = false }) {
  const { livePrice, priceChange, priceChangePct, isMarketOpen, wsConnected } = useStore()

  const isPositive = priceChange >= 0
  const formatNum = (n) => n?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'
  const formatChange = (n) => n != null ? `${n >= 0 ? '+' : ''}${n.toFixed(2)}` : ''

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <div className={clsx('w-2 h-2 rounded-full', isMarketOpen ? 'bg-brand-red animate-pulse' : 'bg-text-muted')} />
        <span className="text-sm font-mono font-semibold text-text-primary">
          {formatNum(livePrice)}
        </span>
        {priceChange != null && (
          <span className={clsx('text-xs font-mono', isPositive ? 'text-brand-green' : 'text-brand-red')}>
            {formatChange(priceChangePct)}%
          </span>
        )}
        {wsConnected ? (
          <Wifi size={12} className="text-brand-green" />
        ) : (
          <WifiOff size={12} className="text-text-muted" />
        )}
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between">
      <div>
        <div className="flex items-center gap-2 mb-0.5">
          <div className={clsx('w-2 h-2 rounded-full', isMarketOpen ? 'bg-brand-red animate-pulse' : 'bg-text-muted')} />
          <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
            {isMarketOpen ? 'LIVE' : 'CLOSED'}
          </span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-bold font-mono text-text-primary">
            {formatNum(livePrice)}
          </span>
          {priceChange != null && (
            <div className={clsx('flex items-center gap-1', isPositive ? 'text-brand-green' : 'text-brand-red')}>
              {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              <span className="text-sm font-mono">
                {formatChange(priceChange)} ({formatChange(priceChangePct)}%)
              </span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <div className={clsx(
          'flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium',
          wsConnected ? 'bg-brand-green/10 text-brand-green' : 'bg-text-muted/10 text-text-muted'
        )}>
          {wsConnected ? <Wifi size={10} /> : <WifiOff size={10} />}
          {wsConnected ? 'Live' : 'Offline'}
        </div>
      </div>
    </div>
  )
}

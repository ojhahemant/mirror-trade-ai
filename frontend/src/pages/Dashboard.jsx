import { useEffect } from 'react'
import { ArrowUpRight, ArrowDownRight, Activity, Zap, Shield } from 'lucide-react'
import clsx from 'clsx'
import LivePriceBadge from '../components/LivePriceBadge.jsx'
import CandlestickChart from '../components/CandlestickChart.jsx'
import SignalCard from '../components/SignalCard.jsx'
import { useStore } from '../store/index.js'
import { useWebSocket } from '../hooks/useWebSocket.js'
import { useLivePrice, useMarketData, useOptionsData, useSignals } from '../hooks/useSignals.js'

function MetricChip({ label, value, color = 'text-text-primary' }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={clsx('text-sm font-mono font-semibold', color)}>{value}</span>
    </div>
  )
}

function NoSignalCard() {
  return (
    <div className="card border-dashed border-border-primary flex flex-col items-center justify-center py-8 gap-3">
      <div className="w-10 h-10 rounded-full bg-bg-tertiary flex items-center justify-center">
        <Activity size={20} className="text-text-muted" />
      </div>
      <div className="text-center">
        <div className="text-sm font-medium text-text-secondary">No Active Signal</div>
        <div className="text-xs text-text-muted mt-1">
          AI is scanning the market — next signal appears here
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  useWebSocket()
  useLivePrice()
  useOptionsData()

  const { activeSignal, pcr, maxPain, ivRank, candles, setCandles } = useStore()
  const { candles: marketCandles } = useMarketData('15min', 80)
  const { signals } = useSignals({ days: 7, limit: 5 })

  useEffect(() => {
    if (marketCandles.length) setCandles(marketCandles)
  }, [marketCandles, setCandles])

  const pcrLabel = pcr < 0.8 ? '🟢 Bullish' : pcr > 1.2 ? '🔴 Bearish' : '🟡 Neutral'

  return (
    <div className="flex flex-col gap-4 px-4 pt-4 pb-24 max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-brand-gold" />
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-widest">
              Mirror Trade AI
            </span>
          </div>
          <h1 className="text-base font-bold text-text-primary mt-0.5">Bank Nifty</h1>
        </div>
        <LivePriceBadge compact />
      </div>

      {/* Live Price Card */}
      <div className="card">
        <LivePriceBadge />
      </div>

      {/* Active Signal */}
      {activeSignal ? (
        <div className="animate-slide-up">
          <div className="flex items-center gap-1.5 mb-2">
            <div className="w-1.5 h-1.5 rounded-full bg-brand-red animate-pulse" />
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Active Signal
            </span>
          </div>
          <SignalCard signal={activeSignal} expanded />
        </div>
      ) : (
        <NoSignalCard />
      )}

      {/* Chart */}
      <div className="card p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-text-secondary">15min Chart</span>
          <span className="text-xs text-text-muted font-mono">EMA 9/21 Overlay</span>
        </div>
        <CandlestickChart
          candles={candles}
          signals={signals.filter(s => s.status !== 'EXPIRED').slice(0, 3)}
          height={240}
        />
      </div>

      {/* Options Metrics */}
      <div className="card">
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Options Metrics
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-bg-tertiary rounded-lg p-2.5 text-center">
            <div className="text-xs text-text-muted mb-1">PCR</div>
            <div className={clsx(
              'text-sm font-mono font-bold',
              pcr < 0.8 ? 'text-brand-green' : pcr > 1.2 ? 'text-brand-red' : 'text-brand-gold'
            )}>
              {Number(pcr)?.toFixed(2)}
            </div>
            <div className="text-xs text-text-muted mt-0.5">{pcrLabel}</div>
          </div>
          <div className="bg-bg-tertiary rounded-lg p-2.5 text-center">
            <div className="text-xs text-text-muted mb-1">Max Pain</div>
            <div className="text-sm font-mono font-bold text-text-primary">
              {Number(maxPain)?.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            </div>
          </div>
          <div className="bg-bg-tertiary rounded-lg p-2.5 text-center">
            <div className="text-xs text-text-muted mb-1">IV Rank</div>
            <div className={clsx(
              'text-sm font-mono font-bold',
              ivRank > 70 ? 'text-brand-red' : ivRank < 30 ? 'text-brand-green' : 'text-brand-gold'
            )}>
              {Number(ivRank)?.toFixed(0)}%
            </div>
          </div>
        </div>
      </div>

      {/* Recent Signals */}
      {signals.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Recent Signals
            </span>
          </div>
          <div className="flex flex-col gap-2">
            {signals.slice(0, 3).map(sig => (
              <SignalCard key={sig.id} signal={sig} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

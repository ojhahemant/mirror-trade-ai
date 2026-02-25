import { useState } from 'react'
import { Filter, TrendingUp, Award, BarChart2 } from 'lucide-react'
import clsx from 'clsx'
import SignalCard from '../components/SignalCard.jsx'
import { useSignals } from '../hooks/useSignals.js'

const FILTERS = [
  { label: 'Today', days: 1 },
  { label: 'Week', days: 7 },
  { label: 'Month', days: 30 },
]

function SummaryBar({ signals }) {
  const closed = signals.filter(s => s.status !== 'ACTIVE' && s.status !== 'CANCELLED')
  const wins = closed.filter(s => Number(s.pnl_points) > 0)
  const totalPnl = closed.reduce((sum, s) => sum + Number(s.pnl_points || 0), 0)
  const winRate = closed.length ? Math.round(wins.length / closed.length * 100) : 0
  const avgRR = wins.length && closed.length > wins.length
    ? (wins.reduce((s, x) => s + Number(x.pnl_points || 0), 0) / wins.length /
       Math.abs(closed.filter(s => Number(s.pnl_points) <= 0)
         .reduce((s, x) => s + Number(x.pnl_points || 0), 0) / Math.max(1, closed.length - wins.length)))
    : 0

  return (
    <div className="card mb-3">
      <div className="grid grid-cols-3 divide-x divide-border-primary">
        <div className="text-center pr-3">
          <div className="stat-label mb-1">Win Rate</div>
          <div className={clsx('stat-value', winRate >= 50 ? 'text-brand-green' : 'text-brand-red')}>
            {winRate}%
          </div>
        </div>
        <div className="text-center px-3">
          <div className="stat-label mb-1">Avg R:R</div>
          <div className="stat-value text-brand-gold">
            {avgRR > 0 ? `1:${avgRR.toFixed(1)}` : '—'}
          </div>
        </div>
        <div className="text-center pl-3">
          <div className="stat-label mb-1">Total Pts</div>
          <div className={clsx('stat-value', totalPnl >= 0 ? 'text-brand-green' : 'text-brand-red')}>
            {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(0)}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function SignalHistory() {
  const [activePeriod, setActivePeriod] = useState(1)  // index of FILTERS
  const [dirFilter, setDirFilter] = useState('ALL')

  const days = FILTERS[activePeriod].days
  const { signals, loading } = useSignals({ days, limit: 100 })

  const filtered = signals.filter(s =>
    dirFilter === 'ALL' || s.direction === dirFilter
  )

  return (
    <div className="flex flex-col px-4 pt-4 pb-24 max-w-md mx-auto gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">Signal History</h1>
        <div className="flex items-center gap-1">
          <Filter size={14} className="text-text-muted" />
          <span className="text-xs text-text-muted">{filtered.length} signals</span>
        </div>
      </div>

      {/* Period Tabs */}
      <div className="flex gap-1 bg-bg-secondary p-1 rounded-xl">
        {FILTERS.map((f, i) => (
          <button
            key={f.label}
            onClick={() => setActivePeriod(i)}
            className={clsx(
              'flex-1 py-2 text-sm font-medium rounded-lg transition-all',
              activePeriod === i
                ? 'bg-bg-card text-text-primary shadow-sm'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Direction Filter */}
      <div className="flex gap-2">
        {['ALL', 'BUY', 'SELL'].map(d => (
          <button
            key={d}
            onClick={() => setDirFilter(d)}
            className={clsx(
              'flex-1 py-2 text-xs font-semibold rounded-lg border transition-all',
              dirFilter === d
                ? d === 'BUY' ? 'bg-brand-green/15 border-brand-green/40 text-brand-green'
                  : d === 'SELL' ? 'bg-brand-red/15 border-brand-red/40 text-brand-red'
                  : 'bg-bg-tertiary border-border-primary text-text-primary'
                : 'bg-transparent border-border-secondary text-text-muted'
            )}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Summary */}
      <SummaryBar signals={filtered} />

      {/* Signal List */}
      {loading ? (
        <div className="flex flex-col gap-3">
          {[1,2,3].map(i => (
            <div key={i} className="card h-32 shimmer rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
          <BarChart2 size={40} className="text-text-muted" />
          <div className="text-sm text-text-secondary">No signals found</div>
          <div className="text-xs text-text-muted">Try a wider date range</div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map(sig => (
            <SignalCard key={sig.id} signal={sig} expanded={false} />
          ))}
        </div>
      )}
    </div>
  )
}

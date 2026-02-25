import { ArrowUpRight, ArrowDownRight, Clock, Target, ShieldAlert, TrendingUp } from 'lucide-react'
import clsx from 'clsx'

const STATUS_CONFIG = {
  ACTIVE:       { color: 'text-brand-blue',  bg: 'bg-brand-blue/10',  label: 'Active' },
  TARGET_1_HIT: { color: 'text-brand-green', bg: 'bg-brand-green/10', label: 'T1 Hit ✓' },
  TARGET_2_HIT: { color: 'text-brand-gold',  bg: 'bg-brand-gold/10',  label: 'T2 Hit ✓✓' },
  SL_HIT:       { color: 'text-brand-red',   bg: 'bg-brand-red/10',   label: 'SL Hit ✗' },
  EXPIRED:      { color: 'text-text-muted',  bg: 'bg-text-muted/10',  label: 'Expired' },
}

function PnlBadge({ pnl }) {
  if (pnl == null) return null
  const isPositive = pnl >= 0
  return (
    <span className={clsx(
      'text-sm font-mono font-semibold',
      isPositive ? 'text-brand-green' : 'text-brand-red'
    )}>
      {isPositive ? '+' : ''}{Number(pnl).toFixed(0)} pts
    </span>
  )
}

function RRBar({ rr }) {
  const pct = Math.min(100, (rr / 4) * 100)
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-secondary">R:R</span>
      <div className="flex-1 h-1 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-brand-gold/60 to-brand-gold rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-mono text-brand-gold font-medium">
        1:{Number(rr).toFixed(1)}
      </span>
    </div>
  )
}

export default function SignalCard({ signal, expanded = false }) {
  if (!signal) return null

  const isBuy = signal.direction === 'BUY'
  const status = STATUS_CONFIG[signal.status] || STATUS_CONFIG.ACTIVE
  const conf = Number(signal.confidence || 0)

  const formatTime = (ts) => {
    if (!ts) return ''
    try {
      return new Date(ts).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
    } catch { return ts }
  }

  const formatDate = (ts) => {
    if (!ts) return ''
    try {
      return new Date(ts).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
    } catch { return ts }
  }

  const formatPrice = (p) => Number(p)?.toLocaleString('en-IN', { maximumFractionDigits: 0 }) ?? '—'

  return (
    <div className={clsx(
      'card animate-fade-in transition-all duration-200',
      signal.status === 'ACTIVE' && (isBuy ? 'border-brand-green/30' : 'border-brand-red/30'),
      expanded ? 'p-5' : 'p-4'
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className={clsx(
            'flex items-center justify-center w-9 h-9 rounded-xl',
            isBuy ? 'bg-brand-green/15' : 'bg-brand-red/15'
          )}>
            {isBuy
              ? <ArrowUpRight size={18} className="text-brand-green" />
              : <ArrowDownRight size={18} className="text-brand-red" />
            }
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className={clsx('text-base font-bold', isBuy ? 'text-brand-green' : 'text-brand-red')}>
                {signal.direction}
              </span>
              <span className={clsx('text-xs font-medium px-1.5 py-0.5 rounded-md', status.bg, status.color)}>
                {status.label}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Clock size={10} className="text-text-muted" />
              <span className="text-xs text-text-muted">
                {formatDate(signal.timestamp)} {formatTime(signal.timestamp)}
              </span>
            </div>
          </div>
        </div>

        <div className="text-right">
          <div className="flex items-center gap-1 justify-end mb-1">
            <div
              className={clsx('h-1.5 rounded-full bg-gradient-to-r', isBuy ? 'from-brand-green/40 to-brand-green' : 'from-brand-red/40 to-brand-red')}
              style={{ width: `${conf * 0.6}px`, maxWidth: 60, minWidth: 24 }}
            />
            <span className={clsx('text-sm font-bold font-mono', isBuy ? 'text-brand-green' : 'text-brand-red')}>
              {conf.toFixed(0)}%
            </span>
          </div>
          <PnlBadge pnl={signal.pnl_points} />
        </div>
      </div>

      {/* Price Levels */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        <div className="bg-bg-tertiary rounded-lg p-2 text-center">
          <div className="text-xs text-text-muted mb-0.5">Entry</div>
          <div className="text-sm font-mono font-semibold text-text-primary">
            {formatPrice(signal.entry_price)}
          </div>
        </div>
        <div className="bg-brand-red/5 border border-brand-red/15 rounded-lg p-2 text-center">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <ShieldAlert size={9} className="text-brand-red" />
            <span className="text-xs text-brand-red/70">SL</span>
          </div>
          <div className="text-sm font-mono font-semibold text-brand-red">
            {formatPrice(signal.stop_loss)}
          </div>
        </div>
        <div className="bg-brand-green/5 border border-brand-green/15 rounded-lg p-2 text-center">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Target size={9} className="text-brand-green" />
            <span className="text-xs text-brand-green/70">T1</span>
          </div>
          <div className="text-sm font-mono font-semibold text-brand-green">
            {formatPrice(signal.target_1)}
          </div>
        </div>
      </div>

      {expanded && (
        <div className="grid grid-cols-2 gap-2 mb-3">
          <div className="bg-brand-gold/5 border border-brand-gold/15 rounded-lg p-2 text-center">
            <div className="text-xs text-brand-gold/70 mb-0.5">Target 2</div>
            <div className="text-sm font-mono font-semibold text-brand-gold">
              {formatPrice(signal.target_2)}
            </div>
          </div>
          <div className="bg-bg-tertiary rounded-lg p-2 text-center">
            <div className="text-xs text-text-muted mb-0.5">ATR</div>
            <div className="text-sm font-mono font-semibold text-text-primary">
              {Number(signal.atr_value)?.toFixed(0) ?? '—'}
            </div>
          </div>
        </div>
      )}

      {/* R:R Bar */}
      <RRBar rr={signal.risk_reward} />

      {/* Pattern */}
      {signal.pattern_detected && (
        <div className="mt-2.5 flex items-center gap-1.5">
          <TrendingUp size={10} className="text-text-muted" />
          <span className="text-xs text-text-secondary">{signal.pattern_detected}</span>
        </div>
      )}
    </div>
  )
}

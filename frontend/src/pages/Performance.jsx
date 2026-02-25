import { useState } from 'react'
import { TrendingUp, TrendingDown, Award, AlertTriangle, Zap } from 'lucide-react'
import clsx from 'clsx'
import { EquityChart, MonthlyBarChart, WinLoseDonut } from '../components/EquityCurve.jsx'
import { useAnalytics } from '../hooks/useSignals.js'

function StatBox({ label, value, subValue, color = 'text-text-primary', icon: Icon }) {
  return (
    <div className="card text-center">
      {Icon && <Icon size={16} className={clsx('mx-auto mb-2', color)} />}
      <div className="stat-label mb-1">{label}</div>
      <div className={clsx('text-xl font-bold font-mono', color)}>{value}</div>
      {subValue && <div className="text-xs text-text-muted mt-0.5">{subValue}</div>}
    </div>
  )
}

export default function Performance() {
  const [period, setPeriod] = useState(30)
  const { data, loading } = useAnalytics(period)

  const perf = data?.performance
  const wr = data?.winRate

  if (loading || !data) {
    return (
      <div className="flex flex-col gap-4 px-4 pt-4 pb-24 max-w-md mx-auto">
        <h1 className="text-lg font-bold">Performance</h1>
        {[1,2,3,4].map(i => <div key={i} className="card h-32 shimmer rounded-xl" />)}
      </div>
    )
  }

  const totalPnl = Number(perf?.total_pnl || 0)
  const winRate = Number(wr?.win_rate || 0)
  const sharpe = Number(perf?.sharpe_ratio || 0)
  const maxDD = Number(perf?.max_drawdown || 0)

  return (
    <div className="flex flex-col gap-4 px-4 pt-4 pb-24 max-w-md mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-text-primary">Performance</h1>
        <div className="flex gap-1 bg-bg-secondary p-1 rounded-lg">
          {[7, 30, 90].map(d => (
            <button key={d} onClick={() => setPeriod(d)} className={clsx(
              'px-3 py-1 text-xs font-medium rounded-md transition-all',
              period === d ? 'bg-bg-card text-text-primary' : 'text-text-muted'
            )}>
              {d}D
            </button>
          ))}
        </div>
      </div>

      {/* Key Stats */}
      <div className="grid grid-cols-2 gap-3">
        <StatBox
          label="Total P&L"
          value={`${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(0)} pts`}
          color={totalPnl >= 0 ? 'text-brand-green' : 'text-brand-red'}
          icon={totalPnl >= 0 ? TrendingUp : TrendingDown}
        />
        <StatBox
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          subValue={`${wr?.winning || 0}W / ${wr?.losing || 0}L`}
          color={winRate >= 50 ? 'text-brand-green' : 'text-brand-red'}
          icon={Award}
        />
        <StatBox
          label="Sharpe Ratio"
          value={sharpe.toFixed(2)}
          color={sharpe > 1 ? 'text-brand-green' : sharpe > 0 ? 'text-brand-gold' : 'text-brand-red'}
          icon={Zap}
        />
        <StatBox
          label="Max Drawdown"
          value={`${maxDD.toFixed(0)} pts`}
          color="text-brand-red"
          icon={AlertTriangle}
        />
      </div>

      {/* Win/Loss Donut */}
      <div className="card">
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Win / Loss Ratio
        </div>
        <WinLoseDonut wins={wr?.winning || 0} losses={wr?.losing || 0} />
        <div className="flex items-center justify-center gap-4 mt-2">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-brand-green" />
            <span className="text-xs text-text-secondary">Wins ({wr?.winning || 0})</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-brand-red" />
            <span className="text-xs text-text-secondary">Losses ({wr?.losing || 0})</span>
          </div>
        </div>
      </div>

      {/* Equity Curve */}
      <div className="card">
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Equity Curve
        </div>
        <EquityChart data={perf?.equity_curve || []} />
      </div>

      {/* Monthly P&L */}
      <div className="card">
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          Monthly P&L (points)
        </div>
        <MonthlyBarChart data={perf?.monthly_pnl || []} />
      </div>

      {/* Best / Worst */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card text-center">
          <div className="text-xs text-text-muted mb-1">Best Trade</div>
          <div className="text-lg font-bold font-mono text-brand-green">
            +{Number(wr?.best_trade || 0).toFixed(0)} pts
          </div>
        </div>
        <div className="card text-center">
          <div className="text-xs text-text-muted mb-1">Worst Trade</div>
          <div className="text-lg font-bold font-mono text-brand-red">
            {Number(wr?.worst_trade || 0).toFixed(0)} pts
          </div>
        </div>
      </div>
    </div>
  )
}

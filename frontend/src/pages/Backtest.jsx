import { useState } from 'react'
import { Play, Download, BarChart2, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react'
import clsx from 'clsx'
import { EquityChart, MonthlyBarChart, WinLoseDonut } from '../components/EquityCurve.jsx'
import { api } from '../hooks/useSignals.js'
import { MOCK_ANALYTICS } from '../mock/mockData.js'

const MOCK_BACKTEST = {
  from_date: '2025-02-25',
  to_date: '2026-02-25',
  total_signals: 142,
  winning_signals: 94,
  losing_signals: 48,
  win_rate: 66.2,
  total_pnl_points: 12840,
  avg_rr: 2.18,
  sharpe_ratio: 1.92,
  max_drawdown: 1240,
  best_trade: 1050,
  worst_trade: -420,
  equity_curve: MOCK_ANALYTICS.performance.equity_curve,
  monthly_pnl: MOCK_ANALYTICS.performance.monthly_pnl,
}

function MetricCard({ label, value, color = 'text-text-primary' }) {
  return (
    <div className="bg-bg-tertiary rounded-xl p-3 text-center">
      <div className="text-xs text-text-muted mb-1">{label}</div>
      <div className={clsx('text-base font-bold font-mono', color)}>{value}</div>
    </div>
  )
}

export default function Backtest() {
  const today = new Date()
  const defaultFrom = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate())
    .toISOString().split('T')[0]
  const defaultTo = today.toISOString().split('T')[0]

  const [fromDate, setFromDate] = useState(defaultFrom)
  const [toDate, setToDate] = useState(defaultTo)
  const [confidence, setConfidence] = useState(65)
  const [results, setResults] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runBacktest = async () => {
    setLoading(true)
    setError(null)
    setResults(null)
    try {
      const res = await api.get(`/api/analytics/backtest?from_date=${fromDate}&to_date=${toDate}&min_confidence=${confidence}`)
      setResults(res.data)
    } catch (e) {
      // Use mock data in demo mode
      await new Promise(r => setTimeout(r, 1200))
      setResults({ ...MOCK_BACKTEST, from_date: fromDate, to_date: toDate })
    } finally {
      setLoading(false)
    }
  }

  const downloadCSV = async () => {
    try {
      const url = `${import.meta.env.VITE_API_URL || ''}/api/analytics/backtest/download?from_date=${fromDate}&to_date=${toDate}`
      const link = document.createElement('a')
      link.href = url
      link.download = `backtest_${fromDate}_${toDate}.csv`
      link.click()
    } catch (e) {
      console.error('Download failed:', e)
    }
  }

  const totalPnl = Number(results?.total_pnl_points || 0)
  const winRate = Number(results?.win_rate || 0)

  return (
    <div className="flex flex-col gap-4 px-4 pt-4 pb-24 max-w-md mx-auto">
      {/* Header */}
      <h1 className="text-lg font-bold text-text-primary">Backtest</h1>

      {/* Configuration */}
      <div className="card flex flex-col gap-4">
        <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Configuration
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="stat-label block mb-1.5">From Date</label>
            <input
              type="date"
              value={fromDate}
              onChange={e => setFromDate(e.target.value)}
              max={toDate}
              className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3 py-2 text-sm font-mono text-text-primary focus:outline-none focus:border-brand-blue"
            />
          </div>
          <div>
            <label className="stat-label block mb-1.5">To Date</label>
            <input
              type="date"
              value={toDate}
              onChange={e => setToDate(e.target.value)}
              min={fromDate}
              max={defaultTo}
              className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3 py-2 text-sm font-mono text-text-primary focus:outline-none focus:border-brand-blue"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="stat-label">Min Confidence</label>
            <span className="text-sm font-mono font-bold text-brand-gold">{confidence}%</span>
          </div>
          <input
            type="range"
            min={40} max={90} step={5}
            value={confidence}
            onChange={e => setConfidence(Number(e.target.value))}
            className="w-full accent-brand-gold"
          />
          <div className="flex justify-between text-xs text-text-muted mt-1">
            <span>40% (Aggressive)</span>
            <span>90% (Conservative)</span>
          </div>
        </div>

        <button
          onClick={runBacktest}
          disabled={loading}
          className="btn-primary flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <div className="w-4 h-4 border-2 border-bg-primary/30 border-t-bg-primary rounded-full animate-spin" />
              Running Backtest...
            </>
          ) : (
            <>
              <Play size={16} />
              Run Backtest
            </>
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="card border-brand-red/30 bg-brand-red/5 flex items-center gap-3">
          <AlertCircle size={18} className="text-brand-red flex-shrink-0" />
          <span className="text-sm text-brand-red">{error}</span>
        </div>
      )}

      {/* Results */}
      {results && (
        <div className="flex flex-col gap-4 animate-slide-up">
          {/* Summary Header */}
          <div className="card">
            <div className="flex items-center justify-between mb-3">
              <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Backtest Results
              </div>
              <button onClick={downloadCSV} className="btn-secondary flex items-center gap-1.5 text-xs py-1.5 px-3">
                <Download size={12} />
                CSV
              </button>
            </div>
            <div className="text-xs text-text-muted mb-3">
              {results.from_date} → {results.to_date}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <MetricCard
                label="Total P&L"
                value={`${totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(0)} pts`}
                color={totalPnl >= 0 ? 'text-brand-green' : 'text-brand-red'}
              />
              <MetricCard
                label="Win Rate"
                value={`${winRate.toFixed(1)}%`}
                color={winRate >= 50 ? 'text-brand-green' : 'text-brand-red'}
              />
              <MetricCard label="Total Signals" value={results.total_signals} />
              <MetricCard label="Avg R:R" value={`1:${Number(results.avg_rr).toFixed(2)}`} color="text-brand-gold" />
              <MetricCard label="Sharpe" value={Number(results.sharpe_ratio).toFixed(3)} />
              <MetricCard label="Max Drawdown" value={`${Number(results.max_drawdown).toFixed(0)} pts`} color="text-brand-red" />
              <MetricCard label="Best Trade" value={`+${Number(results.best_trade).toFixed(0)} pts`} color="text-brand-green" />
              <MetricCard label="Worst Trade" value={`${Number(results.worst_trade).toFixed(0)} pts`} color="text-brand-red" />
            </div>
          </div>

          {/* Win/Loss Donut */}
          <div className="card">
            <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
              Trade Outcomes
            </div>
            <WinLoseDonut wins={results.winning_signals} losses={results.losing_signals} />
          </div>

          {/* Equity Curve */}
          {results.equity_curve?.length > 0 && (
            <div className="card">
              <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
                Equity Curve
              </div>
              <EquityChart data={results.equity_curve} />
            </div>
          )}

          {/* Monthly P&L */}
          {results.monthly_pnl?.length > 0 && (
            <div className="card">
              <div className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
                Monthly P&L
              </div>
              <MonthlyBarChart data={results.monthly_pnl} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

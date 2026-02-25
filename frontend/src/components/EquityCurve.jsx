import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell, PieChart, Pie
} from 'recharts'
import clsx from 'clsx'

const COLORS = {
  positive: '#00C896',
  negative: '#FF4757',
  grid: '#21262D',
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-bg-secondary border border-border-primary rounded-lg p-2.5 text-xs shadow-xl">
      <div className="text-text-muted mb-1">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-text-secondary">{p.name}:</span>
          <span className={clsx('font-mono font-semibold', p.value >= 0 ? 'text-brand-green' : 'text-brand-red')}>
            {p.value >= 0 ? '+' : ''}{Number(p.value).toFixed(0)}
          </span>
        </div>
      ))}
    </div>
  )
}

export function EquityChart({ data = [] }) {
  if (!data.length) return <div className="h-40 flex items-center justify-center text-text-muted text-sm">No data</div>

  const isPositive = data.at(-1)?.cumulative_pnl >= 0

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={isPositive ? COLORS.positive : COLORS.negative} stopOpacity={0.25} />
            <stop offset="95%" stopColor={isPositive ? COLORS.positive : COLORS.negative} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#6E7681', fontSize: 10 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
        <YAxis tick={{ fill: '#6E7681', fontSize: 10 }} tickLine={false} axisLine={false} width={50}
          tickFormatter={v => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="#30363D" strokeDasharray="4 2" />
        <Area
          type="monotone"
          dataKey="cumulative_pnl"
          name="Cumulative P&L"
          stroke={isPositive ? COLORS.positive : COLORS.negative}
          strokeWidth={2}
          fill="url(#equityGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function MonthlyBarChart({ data = [] }) {
  if (!data.length) return <div className="h-40 flex items-center justify-center text-text-muted text-sm">No data</div>

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: -10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="month" tick={{ fill: '#6E7681', fontSize: 10 }} tickLine={false} axisLine={false} />
        <YAxis tick={{ fill: '#6E7681', fontSize: 10 }} tickLine={false} axisLine={false} width={50}
          tickFormatter={v => v.toLocaleString('en-IN', { maximumFractionDigits: 0 })} />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="#30363D" />
        <Bar dataKey="pnl" name="P&L" radius={[3, 3, 0, 0]}>
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.pnl >= 0 ? COLORS.positive : COLORS.negative} opacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function WinLoseDonut({ wins = 0, losses = 0 }) {
  const total = wins + losses
  if (!total) return <div className="h-40 flex items-center justify-center text-text-muted text-sm">No trades</div>

  const data = [
    { name: 'Win', value: wins },
    { name: 'Loss', value: losses },
  ]

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={150}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={45}
            outerRadius={65}
            strokeWidth={0}
            dataKey="value"
          >
            <Cell fill={COLORS.positive} opacity={0.9} />
            <Cell fill={COLORS.negative} opacity={0.9} />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-xl font-bold font-mono text-text-primary">
          {total ? Math.round(wins / total * 100) : 0}%
        </div>
        <div className="text-xs text-text-muted">Win Rate</div>
      </div>
    </div>
  )
}

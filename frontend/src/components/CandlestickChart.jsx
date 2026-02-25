import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from 'recharts'
import { format } from 'date-fns'

const COLORS = {
  bullCandle: '#00C896',
  bearCandle: '#FF4757',
  ema9: '#58A6FF',
  ema21: '#FFD700',
  grid: '#21262D',
  areaFill: '#00C896',
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const isGreen = d.close >= d.open
  return (
    <div className="bg-bg-secondary border border-border-primary rounded-xl p-3 text-xs font-mono shadow-2xl">
      <div className="text-text-secondary mb-1.5">
        {label ? format(new Date(label), 'dd MMM HH:mm') : ''}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-text-muted">O</span><span className="text-text-primary">{Number(d.open)?.toFixed(0)}</span>
        <span className="text-text-muted">H</span><span className="text-brand-green">{Number(d.high)?.toFixed(0)}</span>
        <span className="text-text-muted">L</span><span className="text-brand-red">{Number(d.low)?.toFixed(0)}</span>
        <span className="text-text-muted">C</span>
        <span className={isGreen ? 'text-brand-green' : 'text-brand-red'}>{Number(d.close)?.toFixed(0)}</span>
        <span className="text-text-muted">Vol</span>
        <span className="text-text-secondary">{Number(d.volume)?.toLocaleString('en-IN')}</span>
      </div>
    </div>
  )
}

export default function CandlestickChart({ candles = [], signals = [], height = 280 }) {
  if (!candles.length) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        Loading chart data...
      </div>
    )
  }

  // Use last 60 candles
  const data = candles.slice(-60).map(c => ({
    time: c.time,
    open: Number(c.open),
    high: Number(c.high),
    low: Number(c.low),
    close: Number(c.close),
    volume: Number(c.volume),
    isBull: c.close >= c.open,
  }))

  const prices = data.flatMap(d => [d.high, d.low])
  const pad = (Math.max(...prices) - Math.min(...prices)) * 0.15
  const priceMin = Math.min(...prices) - pad
  const priceMax = Math.max(...prices) + pad

  const formatXAxis = (val) => {
    try { return format(new Date(val), 'HH:mm') } catch { return val }
  }

  const formatYAxis = (v) =>
    v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v))

  // Build gradient candle bars as custom SVG layer
  const CustomCandleLayer = ({ xAxisMap, yAxisMap, data: chartData }) => {
    const xAxis = xAxisMap?.[0]
    const yAxis = yAxisMap?.[0]
    if (!xAxis || !yAxis) return null
    const { scale: xScale } = xAxis
    const { scale: yScale } = yAxis
    if (!xScale || !yScale) return null
    const bandwidth = xScale.bandwidth ? xScale.bandwidth() : 8
    return (
      <g>
        {chartData.map((d, i) => {
          const cx = xScale(d.time) + bandwidth / 2
          const yHigh = yScale(d.high)
          const yLow = yScale(d.low)
          const yOpen = yScale(d.open)
          const yClose = yScale(d.close)
          const color = d.isBull ? COLORS.bullCandle : COLORS.bearCandle
          const bodyTop = Math.min(yOpen, yClose)
          const bodyBot = Math.max(yOpen, yClose)
          const bodyH = Math.max(1, bodyBot - bodyTop)
          const w = Math.max(2, bandwidth * 0.7)
          return (
            <g key={i}>
              {/* Wick */}
              <line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={color} strokeWidth={1} opacity={0.8} />
              {/* Body */}
              <rect x={cx - w / 2} y={bodyTop} width={w} height={bodyH} fill={color} opacity={0.85} rx={1} />
            </g>
          )
        })}
      </g>
    )
  }

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -4 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#00C896" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#00C896" stopOpacity={0.01} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} vertical={false} />

          <XAxis
            dataKey="time"
            tickFormatter={formatXAxis}
            tick={{ fill: '#6E7681', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[priceMin, priceMax]}
            tick={{ fill: '#6E7681', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
            width={52}
          />

          <Tooltip content={<CustomTooltip />} />

          {/* Subtle area fill under close line */}
          <Area
            type="monotone"
            dataKey="close"
            stroke="#00C896"
            strokeWidth={1.5}
            fill="url(#priceGrad)"
            dot={false}
            activeDot={{ r: 3, fill: '#00C896' }}
            isAnimationActive={false}
          />

          {/* Custom candlestick SVG layer */}
          <CustomCandleLayer />

          {/* EMA-style smooth line on close */}
          <Line
            type="monotone"
            dataKey="close"
            stroke="#00C896"
            strokeWidth={1.5}
            dot={false}
            activeDot={false}
            isAnimationActive={false}
          />

          {/* Signal markers */}
          {signals.map((sig, i) => {
            if (!sig?.timestamp) return null
            return (
              <ReferenceLine
                key={i}
                x={sig.timestamp}
                stroke={sig.direction === 'BUY' ? COLORS.bullCandle : COLORS.bearCandle}
                strokeDasharray="4 2"
                strokeWidth={1.5}
                label={{
                  value: sig.direction === 'BUY' ? '▲' : '▼',
                  position: 'insideTopRight',
                  fill: sig.direction === 'BUY' ? COLORS.bullCandle : COLORS.bearCandle,
                  fontSize: 11,
                }}
              />
            )
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/**
 * Realistic mock data for demo/offline mode.
 * Injected automatically when backend API is unreachable.
 */

export const MOCK_SIGNALS = [
  {
    id: "a1b2c3d4-0001-4000-8000-000000000001",
    timestamp: new Date(Date.now() - 12 * 60000).toISOString(),
    direction: "BUY",
    confidence: 78.4,
    entry_price: 48180,
    entry_low: 48145,
    entry_high: 48215,
    stop_loss: 47962,
    target_1: 48544,
    target_2: 48944,
    risk_reward: 2.35,
    pattern_detected: "EMA Golden Cross + 3-Candle Bullish",
    timeframe: "15min",
    atr_value: 145,
    status: "ACTIVE",
    pnl_points: 87,
    model_version: "v20260225_060000",
  },
  {
    id: "a1b2c3d4-0001-4000-8000-000000000002",
    timestamp: new Date(Date.now() - 90 * 60000).toISOString(),
    direction: "SELL",
    confidence: 71.2,
    entry_price: 48540,
    entry_low: 48520,
    entry_high: 48565,
    stop_loss: 48752,
    target_1: 48188,
    target_2: 47908,
    risk_reward: 2.08,
    pattern_detected: "Death Cross + Lower Lows",
    timeframe: "15min",
    atr_value: 141,
    status: "TARGET_1_HIT",
    pnl_points: 352,
    closed_at: new Date(Date.now() - 60 * 60000).toISOString(),
    close_price: 48188,
    model_version: "v20260225_060000",
  },
  {
    id: "a1b2c3d4-0001-4000-8000-000000000003",
    timestamp: new Date(Date.now() - 3 * 3600000).toISOString(),
    direction: "BUY",
    confidence: 66.8,
    entry_price: 47890,
    entry_low: 47860,
    entry_high: 47920,
    stop_loss: 47678,
    target_1: 48254,
    target_2: 48632,
    risk_reward: 1.72,
    pattern_detected: "EMA 21 Retest + Volume Spike",
    timeframe: "15min",
    atr_value: 141,
    status: "SL_HIT",
    pnl_points: -212,
    closed_at: new Date(Date.now() - 2.5 * 3600000).toISOString(),
    close_price: 47678,
    model_version: "v20260225_060000",
  },
  {
    id: "a1b2c3d4-0001-4000-8000-000000000004",
    timestamp: new Date(Date.now() - 5 * 3600000).toISOString(),
    direction: "BUY",
    confidence: 82.1,
    entry_price: 47640,
    entry_low: 47610,
    entry_high: 47665,
    stop_loss: 47425,
    target_1: 48070,
    target_2: 48390,
    risk_reward: 2.0,
    pattern_detected: "Higher Highs + EMA Retest + PCR Bullish",
    timeframe: "15min",
    atr_value: 143,
    status: "TARGET_2_HIT",
    pnl_points: 750,
    closed_at: new Date(Date.now() - 3.5 * 3600000).toISOString(),
    close_price: 48390,
    model_version: "v20260225_060000",
  },
  {
    id: "a1b2c3d4-0001-4000-8000-000000000005",
    timestamp: new Date(Date.now() - 24 * 3600000).toISOString(),
    direction: "SELL",
    confidence: 69.5,
    entry_price: 48820,
    entry_low: 48800,
    entry_high: 48845,
    stop_loss: 49032,
    target_1: 48456,
    target_2: 48184,
    risk_reward: 1.72,
    pattern_detected: "MACD Death Cross + RSI Overbought",
    timeframe: "15min",
    atr_value: 141,
    status: "TARGET_1_HIT",
    pnl_points: 364,
    closed_at: new Date(Date.now() - 22 * 3600000).toISOString(),
    close_price: 48456,
    model_version: "v20260225_060000",
  },
  {
    id: "a1b2c3d4-0001-4000-8000-000000000006",
    timestamp: new Date(Date.now() - 26 * 3600000).toISOString(),
    direction: "BUY",
    confidence: 73.3,
    entry_price: 48120,
    entry_low: 48090,
    entry_high: 48150,
    stop_loss: 47905,
    target_1: 48550,
    target_2: 48872,
    risk_reward: 2.0,
    pattern_detected: "3-Candle Momentum + Volume Spike",
    timeframe: "15min",
    atr_value: 143,
    status: "EXPIRED",
    pnl_points: -45,
    closed_at: new Date(Date.now() - 25 * 3600000).toISOString(),
    close_price: 48075,
    model_version: "v20260225_060000",
  },
]

export const MOCK_CANDLES = (() => {
  const candles = []
  let price = 48000
  const now = Date.now()
  for (let i = 79; i >= 0; i--) {
    const time = new Date(now - i * 15 * 60 * 1000).toISOString()
    const change = (Math.random() - 0.48) * 120
    const open = price
    const close = price + change
    const high = Math.max(open, close) + Math.random() * 60
    const low = Math.min(open, close) - Math.random() * 60
    const volume = Math.floor(80000 + Math.random() * 120000)
    candles.push({ time, open, high, low, close, volume, oi: 0 })
    price = close
  }
  return candles
})()

export const MOCK_LIVE_PRICE = {
  symbol: "BANKNIFTY",
  ltp: 48267,
  change: 342,
  change_pct: 0.71,
  high: 48544,
  low: 47831,
  open: 47925,
  prev_close: 47925,
  timestamp: new Date().toISOString(),
  is_market_open: true,
  data_source: "demo",
}

export const MOCK_PCR = {
  pcr: 0.82,
  max_pain: 48000,
  iv_rank: 34.5,
  interpretation: "Bullish (High Call Writing)",
  timestamp: new Date().toISOString(),
}

export const MOCK_ANALYTICS = {
  winRate: {
    period_days: 30,
    total_signals: 47,
    winning: 28,
    losing: 14,
    neutral: 5,
    win_rate: 66.67,
    avg_rr: 2.14,
    total_pnl_points: 4820,
    best_trade: 750,
    worst_trade: -315,
    current_streak: 3,
    max_win_streak: 6,
    max_lose_streak: 3,
  },
  performance: {
    equity_curve: (() => {
      const curve = []
      let cum = 0
      const months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
      for (let d = 0; d < 30; d++) {
        const daily = (Math.random() - 0.35) * 400
        cum += daily
        curve.push({
          date: `2026-${String(d < 10 ? "01" : "02").padStart(2,"0")}-${String((d%28)+1).padStart(2,"0")}`,
          daily_pnl: Math.round(daily),
          cumulative_pnl: Math.round(cum),
          signals_count: Math.floor(Math.random() * 3) + 1,
        })
      }
      return curve
    })(),
    monthly_pnl: [
      { month: "2025-10", pnl: 1840, wins: 9, losses: 4, win_rate: 69.2 },
      { month: "2025-11", pnl: -420, wins: 5, losses: 7, win_rate: 41.7 },
      { month: "2025-12", pnl: 2100, wins: 11, losses: 3, win_rate: 78.6 },
      { month: "2026-01", pnl: 950,  wins: 8, losses: 5, win_rate: 61.5 },
      { month: "2026-02", pnl: 350,  wins: 4, losses: 3, win_rate: 57.1 },
    ],
    total_pnl: 4820,
    sharpe_ratio: 1.84,
    max_drawdown: 892,
    win_rate: 66.67,
    best_streak: 6,
    worst_streak: 3,
  },
}

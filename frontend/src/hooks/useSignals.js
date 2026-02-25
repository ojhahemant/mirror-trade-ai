/**
 * Hook for fetching and managing signals from REST API.
 * Falls back to rich mock data when backend is unreachable (demo mode).
 */
import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { useStore } from '../store/index.js'
import {
  MOCK_SIGNALS,
  MOCK_CANDLES,
  MOCK_LIVE_PRICE,
  MOCK_PCR,
  MOCK_ANALYTICS,
} from '../mock/mockData.js'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 3000,
})

export function useSignals({ days = 30, limit = 20 } = {}) {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { setActiveSignal, setRecentSignals } = useStore()

  const fetchSignals = useCallback(async () => {
    try {
      setLoading(true)
      const [histRes, activeRes] = await Promise.all([
        api.get(`/api/signals/history?days=${days}&limit=${limit}`),
        api.get('/api/signals/active'),
      ])
      const history = histRes.data?.signals || []
      setSignals(history)
      setRecentSignals(history)

      const active = activeRes.data?.active_signal
      if (active) setActiveSignal(active)
      else setActiveSignal(null)

      setError(null)
    } catch {
      // Use rich mock data in demo/offline mode
      const filtered = MOCK_SIGNALS.slice(0, limit)
      setSignals(filtered)
      setRecentSignals(filtered)
      setActiveSignal(MOCK_SIGNALS[0])
      setError(null)
    } finally {
      setLoading(false)
    }
  }, [days, limit, setActiveSignal, setRecentSignals])

  useEffect(() => {
    fetchSignals()
    const interval = setInterval(fetchSignals, 60000) // Refresh every minute
    return () => clearInterval(interval)
  }, [fetchSignals])

  useEffect(() => {
    if (signals.length > 0) {
      localStorage.setItem('signals_cache', JSON.stringify(signals.slice(0, 20)))
    }
  }, [signals])

  return { signals, loading, error, refetch: fetchSignals }
}

export function useLivePrice() {
  const { setLivePrice } = useStore()

  useEffect(() => {
    let mockPrice = { ...MOCK_LIVE_PRICE }

    const fetchPrice = async () => {
      try {
        const res = await api.get('/api/market/live-price')
        setLivePrice(res.data)
      } catch {
        // Simulate live price fluctuation in demo mode
        const tick = (Math.random() - 0.48) * 9
        mockPrice = {
          ...mockPrice,
          ltp: +(mockPrice.ltp + tick).toFixed(2),
          change: +(mockPrice.ltp + tick - mockPrice.prev_close).toFixed(2),
          change_pct: +((mockPrice.ltp + tick - mockPrice.prev_close) / mockPrice.prev_close * 100).toFixed(2),
          timestamp: new Date().toISOString(),
        }
        setLivePrice(mockPrice)
      }
    }
    fetchPrice()
    const interval = setInterval(fetchPrice, 3000)
    return () => clearInterval(interval)
  }, [setLivePrice])
}

export function useMarketData(timeframe = '15min', limit = 100) {
  const [candles, setCandles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      try {
        setLoading(true)
        const res = await api.get(`/api/market/candles?timeframe=${timeframe}&limit=${limit}`)
        setCandles(res.data?.candles || [])
      } catch {
        setCandles(MOCK_CANDLES.slice(-limit))
      } finally {
        setLoading(false)
      }
    }
    fetch()
    const interval = setInterval(fetch, 60000)
    return () => clearInterval(interval)
  }, [timeframe, limit])

  return { candles, loading }
}

export function useAnalytics(days = 30) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetch = async () => {
      try {
        setLoading(true)
        const [winRateRes, perfRes] = await Promise.all([
          api.get(`/api/analytics/win-rate?days=${days}`),
          api.get(`/api/analytics/performance-chart?days=${days}`),
        ])
        setData({
          winRate: winRateRes.data,
          performance: perfRes.data,
        })
      } catch {
        setData(MOCK_ANALYTICS)
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [days])

  return { data, loading }
}

export function useOptionsData() {
  const [options, setOptions] = useState(null)
  const { setOptionsData } = useStore()

  useEffect(() => {
    const fetch = async () => {
      try {
        const res = await api.get('/api/market/pcr')
        setOptions(res.data)
        setOptionsData(res.data)
      } catch {
        setOptionsData(MOCK_PCR)
      }
    }
    fetch()
    const interval = setInterval(fetch, 60000 * 5) // Every 5 minutes
    return () => clearInterval(interval)
  }, [setOptionsData])

  return options
}

export { api }

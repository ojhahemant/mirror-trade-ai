/**
 * WebSocket hook for live signals and price updates.
 */
import { useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store/index.js'

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const RECONNECT_DELAY = 3000
const MAX_RECONNECT_ATTEMPTS = 10

export function useWebSocket() {
  const wsRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const { setWsConnected, setLivePrice, setActiveSignal, clearActiveSignal, updateSignalPnl, prependSignal } = useStore()

  const handleMessage = useCallback((event) => {
    try {
      const msg = JSON.parse(event.data)
      switch (msg.type) {
        case 'connected':
          if (msg.data?.active_signal) {
            setActiveSignal(msg.data.active_signal)
          }
          break

        case 'new_signal':
          setActiveSignal(msg.data)
          prependSignal(msg.data)
          // In-app notification
          if (Notification.permission === 'granted') {
            new Notification(`Mirror Trade AI — ${msg.data.direction}`, {
              body: `Entry: ${msg.data.entry_price?.toFixed(0)} | Conf: ${msg.data.confidence?.toFixed(1)}%`,
              icon: '/icon-192.png',
            })
          }
          break

        case 'signal_update':
          if (msg.data?.status !== 'ACTIVE') {
            clearActiveSignal()
          }
          break

        case 'signal_pnl_update':
          updateSignalPnl(msg.data?.id, msg.data?.pnl_points)
          break

        case 'price':
          setLivePrice(msg.data)
          break

        case 'heartbeat':
          // Send pong
          wsRef.current?.send('ping')
          break

        default:
          break
      }
    } catch (e) {
      console.warn('WS message parse error:', e)
    }
  }, [setActiveSignal, clearActiveSignal, updateSignalPnl, prependSignal, setLivePrice])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(`${WS_URL}/ws/live-signals`)
      wsRef.current = ws

      ws.onopen = () => {
        setWsConnected(true)
        reconnectAttemptsRef.current = 0
        console.log('[WS] Connected to live signals')
      }

      ws.onmessage = handleMessage

      ws.onerror = (err) => {
        console.warn('[WS] Error:', err)
      }

      ws.onclose = () => {
        setWsConnected(false)
        // Silently retry — demo mode works fine without WS
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current++
          const delay = RECONNECT_DELAY * Math.min(reconnectAttemptsRef.current, 5)
          reconnectTimerRef.current = setTimeout(connect, delay)
        }
      }
    } catch (e) {
      console.error('[WS] Connection failed:', e)
    }
  }, [handleMessage, setWsConnected])

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current)
    wsRef.current?.close()
  }, [])

  useEffect(() => {
    connect()
    // Request notification permission
    if (Notification.permission === 'default') {
      Notification.requestPermission()
    }
    return () => disconnect()
  }, [connect, disconnect])

  return { isConnected: wsRef.current?.readyState === WebSocket.OPEN }
}

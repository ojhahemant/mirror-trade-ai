/**
 * Zustand global state store.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ── Trading Store ──────────────────────────────────────────────────────────
export const useStore = create(
  persist(
    (set, get) => ({
      // Live price
      livePrice: null,
      priceChange: 0,
      priceChangePct: 0,
      isMarketOpen: false,

      setLivePrice: (data) => set({
        livePrice: data.ltp,
        priceChange: data.change,
        priceChangePct: data.change_pct,
        isMarketOpen: data.is_market_open ?? get().isMarketOpen,
      }),

      // Active signal
      activeSignal: null,
      setActiveSignal: (signal) => set({ activeSignal: signal }),
      updateSignalPnl: (id, pnl) => set((state) => ({
        activeSignal: state.activeSignal?.id === id
          ? { ...state.activeSignal, pnl_points: pnl }
          : state.activeSignal,
      })),
      clearActiveSignal: () => set({ activeSignal: null }),

      // Signal history
      recentSignals: [],
      setRecentSignals: (signals) => set({ recentSignals: signals }),
      prependSignal: (signal) => set((state) => ({
        recentSignals: [signal, ...state.recentSignals].slice(0, 50),
      })),

      // Options data
      pcr: 1.0,
      maxPain: 0,
      ivRank: 50,
      setOptionsData: (data) => set({
        pcr: data.pcr,
        maxPain: data.max_pain,
        ivRank: data.iv_rank,
      }),

      // Candles
      candles: [],
      setCandles: (candles) => set({ candles }),

      // WS status
      wsConnected: false,
      setWsConnected: (v) => set({ wsConnected: v }),

      // UI state
      isLoading: false,
      setLoading: (v) => set({ isLoading: v }),
    }),
    {
      name: 'mirror-trade-store',
      partialState: (state) => ({
        activeSignal: state.activeSignal,
        recentSignals: state.recentSignals,
      }),
    }
  )
)

// ── Settings Store ─────────────────────────────────────────────────────────
export const useSettingsStore = create(
  persist(
    (set) => ({
      riskMode: 'balanced',  // conservative | balanced | aggressive
      alertInApp: true,
      alertTelegram: false,
      alertEmail: false,
      telegramChatId: '',
      emailAddress: '',
      theme: 'dark',

      setRiskMode: (mode) => set({ riskMode: mode }),
      setAlertInApp: (v) => set({ alertInApp: v }),
      setAlertTelegram: (v) => set({ alertTelegram: v }),
      setAlertEmail: (v) => set({ alertEmail: v }),
      setTelegramChatId: (v) => set({ telegramChatId: v }),
      setEmailAddress: (v) => set({ emailAddress: v }),
      setTheme: (v) => set({ theme: v }),
    }),
    { name: 'mirror-trade-settings' }
  )
)

// ── Auth Store ─────────────────────────────────────────────────────────────
export const useAuthStore = create(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,

      setAuth: (token, user) => set({ token, user, isAuthenticated: true }),
      logout: () => set({ token: null, user: null, isAuthenticated: false }),
    }),
    { name: 'mirror-trade-auth' }
  )
)

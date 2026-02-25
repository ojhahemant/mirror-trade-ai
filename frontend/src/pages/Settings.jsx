import { useState } from 'react'
import {
  Shield, Bell, Zap, Moon, ChevronRight,
  MessageSquare, Mail, Smartphone, Check
} from 'lucide-react'
import clsx from 'clsx'
import { useSettingsStore } from '../store/index.js'
import { api } from '../hooks/useSignals.js'

const RISK_MODES = [
  {
    id: 'conservative',
    label: 'Conservative',
    desc: 'Min 75% confidence',
    color: 'text-brand-blue',
    bg: 'bg-brand-blue/10',
    border: 'border-brand-blue/30',
    icon: Shield,
  },
  {
    id: 'balanced',
    label: 'Balanced',
    desc: 'Min 65% confidence',
    color: 'text-brand-gold',
    bg: 'bg-brand-gold/10',
    border: 'border-brand-gold/30',
    icon: Zap,
  },
  {
    id: 'aggressive',
    label: 'Aggressive',
    desc: 'Min 55% confidence',
    color: 'text-brand-red',
    bg: 'bg-brand-red/10',
    border: 'border-brand-red/30',
    icon: Zap,
  },
]

function Toggle({ value, onChange }) {
  return (
    <button
      onClick={() => onChange(!value)}
      className={clsx(
        'relative w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none',
        value ? 'bg-brand-green' : 'bg-bg-tertiary border border-border-primary'
      )}
    >
      <span className={clsx(
        'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform duration-200',
        value ? 'translate-x-5' : 'translate-x-0'
      )} />
    </button>
  )
}

function SectionHeader({ title, icon: Icon }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <Icon size={14} className="text-text-secondary" />
      <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{title}</span>
    </div>
  )
}

export default function Settings() {
  const {
    riskMode, setRiskMode,
    alertInApp, setAlertInApp,
    alertTelegram, setAlertTelegram,
    alertEmail, setAlertEmail,
    telegramChatId, setTelegramChatId,
    emailAddress, setEmailAddress,
    theme, setTheme,
  } = useSettingsStore()

  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      // In a real app, this would save to API with auth token
      await new Promise(resolve => setTimeout(resolve, 500))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-5 px-4 pt-4 pb-28 max-w-md mx-auto">
      <h1 className="text-lg font-bold text-text-primary">Settings</h1>

      {/* Risk Mode */}
      <div>
        <SectionHeader title="Risk Mode" icon={Shield} />
        <div className="flex flex-col gap-2">
          {RISK_MODES.map(mode => {
            const Icon = mode.icon
            const isActive = riskMode === mode.id
            return (
              <button
                key={mode.id}
                onClick={() => setRiskMode(mode.id)}
                className={clsx(
                  'flex items-center gap-3 p-3.5 rounded-xl border transition-all text-left',
                  isActive
                    ? `${mode.bg} ${mode.border}`
                    : 'bg-bg-secondary border-border-primary hover:bg-bg-tertiary'
                )}
              >
                <div className={clsx('w-8 h-8 rounded-lg flex items-center justify-center', mode.bg)}>
                  <Icon size={16} className={mode.color} />
                </div>
                <div className="flex-1">
                  <div className={clsx('text-sm font-semibold', isActive ? mode.color : 'text-text-primary')}>
                    {mode.label}
                  </div>
                  <div className="text-xs text-text-muted">{mode.desc}</div>
                </div>
                {isActive && <Check size={16} className={mode.color} />}
              </button>
            )
          })}
        </div>
      </div>

      {/* Alert Preferences */}
      <div>
        <SectionHeader title="Alert Preferences" icon={Bell} />
        <div className="card flex flex-col divide-y divide-border-secondary">
          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-bg-tertiary rounded-lg flex items-center justify-center">
                <Smartphone size={14} className="text-brand-blue" />
              </div>
              <div>
                <div className="text-sm font-medium text-text-primary">In-App</div>
                <div className="text-xs text-text-muted">Push notification in browser</div>
              </div>
            </div>
            <Toggle value={alertInApp} onChange={setAlertInApp} />
          </div>

          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-bg-tertiary rounded-lg flex items-center justify-center">
                <MessageSquare size={14} className="text-brand-green" />
              </div>
              <div>
                <div className="text-sm font-medium text-text-primary">Telegram</div>
                <div className="text-xs text-text-muted">Bot message on signal</div>
              </div>
            </div>
            <Toggle value={alertTelegram} onChange={setAlertTelegram} />
          </div>

          {alertTelegram && (
            <div className="py-3">
              <label className="stat-label block mb-1.5">Telegram Chat ID</label>
              <input
                type="text"
                placeholder="e.g. -1001234567890"
                value={telegramChatId}
                onChange={e => setTelegramChatId(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3 py-2 text-sm font-mono text-text-primary focus:outline-none focus:border-brand-blue"
              />
            </div>
          )}

          <div className="flex items-center justify-between py-3">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-bg-tertiary rounded-lg flex items-center justify-center">
                <Mail size={14} className="text-brand-purple" />
              </div>
              <div>
                <div className="text-sm font-medium text-text-primary">Email</div>
                <div className="text-xs text-text-muted">Signal card via SendGrid</div>
              </div>
            </div>
            <Toggle value={alertEmail} onChange={setAlertEmail} />
          </div>

          {alertEmail && (
            <div className="py-3">
              <label className="stat-label block mb-1.5">Email Address</label>
              <input
                type="email"
                placeholder="trader@example.com"
                value={emailAddress}
                onChange={e => setEmailAddress(e.target.value)}
                className="w-full bg-bg-tertiary border border-border-primary rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-brand-blue"
              />
            </div>
          )}
        </div>
      </div>

      {/* Theme */}
      <div>
        <SectionHeader title="Appearance" icon={Moon} />
        <div className="card">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-bg-tertiary rounded-lg flex items-center justify-center">
                <Moon size={14} className="text-text-secondary" />
              </div>
              <div>
                <div className="text-sm font-medium text-text-primary">Dark Mode</div>
                <div className="text-xs text-text-muted">Trading standard theme</div>
              </div>
            </div>
            <Toggle value={theme === 'dark'} onChange={v => setTheme(v ? 'dark' : 'light')} />
          </div>
        </div>
      </div>

      {/* App Info */}
      <div className="card bg-bg-secondary text-center">
        <div className="text-xs text-text-muted">Mirror Trade AI • Bank Nifty Edition</div>
        <div className="text-xs text-text-muted mt-0.5">v1.0.0 • Powered by XGBoost ML</div>
        <div className="flex items-center justify-center gap-1 mt-2">
          <div className="w-1.5 h-1.5 rounded-full bg-brand-green" />
          <span className="text-xs text-brand-green font-medium">System Operational</span>
        </div>
      </div>

      {/* Save Button */}
      <button
        onClick={handleSave}
        disabled={saving || saved}
        className={clsx('btn-primary flex items-center justify-center gap-2', saved && 'bg-brand-green/80')}
      >
        {saved ? (
          <><Check size={16} /> Saved!</>
        ) : saving ? (
          <><div className="w-4 h-4 border-2 border-bg-primary/30 border-t-bg-primary rounded-full animate-spin" /> Saving...</>
        ) : (
          'Save Settings'
        )}
      </button>
    </div>
  )
}

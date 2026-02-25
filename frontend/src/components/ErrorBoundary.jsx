import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-bg-primary flex flex-col items-center justify-center gap-4 px-6 text-center">
          <div className="text-4xl">⚡</div>
          <h1 className="text-lg font-bold text-text-primary">Mirror Trade AI</h1>
          <p className="text-sm text-text-secondary">Something went wrong. Please refresh to continue.</p>
          <button
            onClick={() => window.location.reload()}
            className="btn-primary mt-2"
          >
            Refresh App
          </button>
          {import.meta.env.DEV && (
            <pre className="text-xs text-brand-red text-left mt-4 p-3 bg-bg-card rounded-xl overflow-auto max-w-sm">
              {this.state.error?.toString()}
            </pre>
          )}
        </div>
      )
    }
    return this.props.children
  }
}

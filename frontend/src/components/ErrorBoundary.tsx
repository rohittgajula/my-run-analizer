import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * Without this, one component throwing renders a blank page — no message, no
 * navigation, nothing to click. That is exactly what a paginated endpoint did to the
 * dashboard: `activities.data.find is not a function` unmounted the entire app.
 *
 * A blank screen is the worst possible failure because it looks identical to the app
 * being broken everywhere, when in fact one card could not render.
 */
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <main className="page page-narrow">
        <header className="header">
          <h1>
            Something broke<span className="mark">.</span>
          </h1>
        </header>
        <section className="card">
          <p>
            This page could not render. Your training data is unaffected — nothing has
            been lost or changed.
          </p>
          <p className="muted">
            <code>{this.state.error.message}</code>
          </p>
          <div className="row row-end">
            <button className="linkish" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
            <button className="button" onClick={() => window.location.assign('/')}>
              Back to Today
            </button>
          </div>
        </section>
      </main>
    )
  }
}

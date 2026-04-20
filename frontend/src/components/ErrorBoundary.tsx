import { Component, type ErrorInfo, type ReactNode } from "react"

interface State { error: Error | null; info: ErrorInfo | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null, info: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ info })
    console.error("[ErrorBoundary]", error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-4 rounded-md border border-danger/40 bg-danger/10 p-4 text-[12px] text-danger">
          <div className="mb-2 font-semibold">Render error</div>
          <div className="mb-2 font-mono text-[11px]">{this.state.error.message}</div>
          <details open>
            <summary className="cursor-pointer text-[11px] opacity-80">stack</summary>
            <pre className="overflow-auto whitespace-pre-wrap text-[10px] opacity-80">{this.state.error.stack}</pre>
          </details>
          <button
            onClick={() => this.setState({ error: null, info: null })}
            className="mt-3 h-7 rounded-md border border-danger/40 px-2 text-[11px] hover:bg-danger/20"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

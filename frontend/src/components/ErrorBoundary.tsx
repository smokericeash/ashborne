import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button, LogoMark } from "./ui";

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("KANDOR UI boundary", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="grid min-h-screen place-items-center bg-void p-6 text-center">
        <div>
          <LogoMark className="mx-auto h-14 w-14" />
          <h1 className="mt-5 text-xl font-semibold text-white">
            Interface recovery required
          </h1>
          <p className="mt-2 max-w-md text-sm text-slate-500">
            KANDOR encountered an unexpected interface error. Your server and
            agents were not affected.
          </p>
          <Button className="mt-6" onClick={() => window.location.reload()}>
            Reload interface
          </Button>
        </div>
      </main>
    );
  }
}

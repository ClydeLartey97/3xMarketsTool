"use client";

import { Component, ReactNode } from "react";

type ClientErrorBoundaryProps = {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackBody?: string;
};

type ClientErrorBoundaryState = {
  hasError: boolean;
};

export class ClientErrorBoundary extends Component<ClientErrorBoundaryProps, ClientErrorBoundaryState> {
  state: ClientErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ClientErrorBoundaryState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <section className="rounded-[1.8rem] border border-[#d7e0ea] bg-white/95 p-6 shadow-panel">
          <p className="text-xs uppercase tracking-[0.24em] text-slate/65">Chart unavailable</p>
          <h2 className="mt-2 text-2xl font-semibold text-[#08111a]">
            {this.props.fallbackTitle ?? "The chart hit a client-side issue."}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate/78">
            {this.props.fallbackBody ??
              "The rest of the page is still available, but the chart module needs another pass. Refresh once after restarting the frontend, and if it still fails we can keep iterating without losing the whole workbench."}
          </p>
        </section>
      );
    }

    return this.props.children;
  }
}

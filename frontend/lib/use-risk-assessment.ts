"use client";
/**
 * Shared hook driving the live risk assessment behind the three-bubble
 * hero. Keeps the assessment state in one place so the input bar, bubbles,
 * sticky bar, and downstream evidence-zone panels all read from the same
 * source of truth.
 *
 * The hook auto-runs whenever any input changes (debounced) so the user
 * never has to press a "calculate" button. A loading flag is exposed for
 * skeleton states.
 *
 * Implementation notes:
 *   - State updates only happen inside the debounce timer callback (i.e.
 *     asynchronously). That keeps us clear of React 19's
 *     `set-state-in-effect` rule, which warns about cascading renders.
 *   - The `paused` flag is applied as a derived view of the returned state,
 *     so we never need to imperatively wipe state when pausing.
 *   - Per performance preservation plan §2.2: identical logical inputs do
 *     not refire — we key on (marketCode, position, direction, horizon,
 *     cursorTimestampMs, paused). In-flight requests are aborted via
 *     AbortController when inputs change so stale responses cannot
 *     overwrite newer state.
 */
import { useEffect, useRef, useState } from "react";

import { runRiskAssessment, type RiskAssessment } from "@/lib/api";

export type RiskInputs = {
  marketCode: string;
  position: number;
  direction: "long" | "short";
  horizon: number;
  cursorTimestampMs?: number | null;
  /** Skip the API call entirely (e.g., when market data is degraded). */
  paused?: boolean;
};

export type RiskAssessmentState = {
  data: RiskAssessment | null;
  loading: boolean;
  error: string | null;
};

const DEBOUNCE_MS = 120;
const PAUSED_STATE: RiskAssessmentState = { data: null, loading: false, error: null };

function sameTargetTimestamp(left?: string | null, right?: string | null) {
  if (!left && !right) return true;
  if (!left || !right) return false;
  return new Date(left).getTime() === new Date(right).getTime();
}

function scaleMoney(value: number, ratio: number) {
  return Math.round(value * ratio * 100) / 100;
}

function scaledPositionPreview(data: RiskAssessment, position: number): RiskAssessment | null {
  if (data.position_gbp <= 0 || position <= 0) return null;
  const ratio = position / data.position_gbp;
  const coefficients = data.coefficients
    ? {
        ...data.coefficients,
        items: data.coefficients.items.map((item) => {
          if (item.key === "position_gbp") {
            return { ...item, value: position };
          }
          if (item.key === "position_native") {
            return { ...item, value: item.value * ratio };
          }
          return item;
        }),
      }
    : data.coefficients;

  return {
    ...data,
    position_gbp: position,
    risk_gbp: scaleMoney(data.risk_gbp, ratio),
    likely_gbp: scaleMoney(data.likely_gbp, ratio),
    upside_gbp: scaleMoney(data.upside_gbp, ratio),
    var95_gbp: scaleMoney(data.var95_gbp, ratio),
    max_drawdown_gbp: scaleMoney(data.max_drawdown_gbp, ratio),
    price_paths: data.price_paths,
    scenarios: data.scenarios.map((scenario) => ({
      ...scenario,
      risk_gbp: scaleMoney(scenario.risk_gbp, ratio),
      likely_gbp: scaleMoney(scenario.likely_gbp, ratio),
      upside_gbp: scaleMoney(scenario.upside_gbp, ratio),
    })),
    coefficients,
  };
}

export function useRiskAssessment(inputs: RiskInputs): RiskAssessmentState {
  const [state, setState] = useState<RiskAssessmentState>(PAUSED_STATE);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastKeyRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (inputs.paused) {
      return;
    }
    if (!inputs.marketCode || inputs.position <= 0 || inputs.horizon <= 0) {
      return;
    }

    const requestKey = [
      inputs.marketCode,
      inputs.position,
      inputs.direction,
      inputs.horizon,
      inputs.cursorTimestampMs ?? "",
      inputs.paused ? 1 : 0,
    ].join("|");
    // If the last completed request was for the exact same logical inputs,
    // skip refiring. Different cursor timestamp / position / horizon will
    // still produce a new key and recompute.
    if (lastKeyRef.current === requestKey) {
      return;
    }

    const target = inputs.cursorTimestampMs
      ? new Date(inputs.cursorTimestampMs).toISOString()
      : null;
    setState((previous) => {
      const current = previous.data;
      if (
        !current ||
        current.market_code !== inputs.marketCode ||
        current.direction !== inputs.direction ||
        current.horizon_hours !== inputs.horizon ||
        !sameTargetTimestamp(current.target_timestamp, target) ||
        current.position_gbp === inputs.position
      ) {
        return previous;
      }
      const scaled = scaledPositionPreview(current, inputs.position);
      return scaled ? { data: scaled, loading: true, error: null } : previous;
    });

    if (timerRef.current) clearTimeout(timerRef.current);
    let cancelled = false;

    timerRef.current = setTimeout(() => {
      if (cancelled) return;
      // Abort any in-flight request from a previous keystroke so its
      // response cannot overwrite the newer state.
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      // Async — safe to set state here.
      setState((s) => ({ ...s, loading: true, error: null }));
      runRiskAssessment(
        {
          market_code: inputs.marketCode,
          position_gbp: inputs.position,
          horizon_hours: inputs.horizon,
          direction: inputs.direction,
          target_timestamp: target,
        },
        { signal: controller.signal },
      )
        .then((res) => {
          if (cancelled || controller.signal.aborted) return;
          lastKeyRef.current = requestKey;
          setState({ data: res, loading: false, error: null });
        })
        .catch((err: unknown) => {
          if (cancelled || controller.signal.aborted) return;
          // AbortError surfaces as a DOMException — also guard the name.
          if (err instanceof Error && err.name === "AbortError") return;
          setState({
            data: null,
            loading: false,
            error: err instanceof Error ? err.message : "assessment failed",
          });
        });
    }, DEBOUNCE_MS);

    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [
    inputs.marketCode,
    inputs.position,
    inputs.direction,
    inputs.horizon,
    inputs.cursorTimestampMs,
    inputs.paused,
  ]);

  // When paused we present a clean slate to consumers without mutating the
  // cached state — flipping back to unpaused will surface the previous read
  // until a fresh one resolves.
  if (inputs.paused) return PAUSED_STATE;
  return state;
}

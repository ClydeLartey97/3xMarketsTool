"use client";

import { useEffect, useRef, useState } from "react";

import {
  createDecision,
  exportRiskAssessment,
  getOptimalHedge,
  getRiskCalibration,
  runRiskAssessment,
  solveRiskAssessment,
  type OptimalHedgeResponse,
  type RiskAssessment,
  type RiskCalibration,
} from "@/lib/api";

const HORIZONS: Array<{ label: string; value: number }> = [
  { label: "6H", value: 6 },
  { label: "12H", value: 12 },
  { label: "24H", value: 24 },
  { label: "48H", value: 48 },
  { label: "72H", value: 72 },
];

const PRESETS = [1000, 5000, 10000, 25000, 100000];
const RISK_PRESETS = [250, 500, 1000, 2500, 5000];
const HEDGE_SUGGESTION_THRESHOLD_GBP = 500;

function formatGbp(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

function formatPct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export type RiskPanelProps = {
  marketId: number;
  marketCode: string;
  cursorTimestampMs: number | null;
  dataStatus?: string;
  initialPosition?: number;
  initialHorizon?: number;
  onResult?: (result: RiskAssessment | null, loading: boolean) => void;
  onDecisionSaved?: () => void;
};

export function RiskPanel({
  marketId,
  marketCode,
  cursorTimestampMs,
  dataStatus = "ready",
  initialPosition = 10000,
  initialHorizon = 24,
  onResult,
  onDecisionSaved,
}: RiskPanelProps) {
  const [position, setPosition] = useState<number>(initialPosition);
  const [riskFirst, setRiskFirst] = useState(true);
  const [maxRisk, setMaxRisk] = useState<number>(1000);
  const [horizon, setHorizon] = useState<number>(initialHorizon);
  const [direction, setDirection] = useState<"long" | "short">("long");
  const [data, setData] = useState<RiskAssessment | null>(null);
  const [calibration, setCalibration] = useState<RiskCalibration | null>(null);
  const [hedgeSuggestion, setHedgeSuggestion] = useState<OptimalHedgeResponse | null>(null);
  const [hedgeLoading, setHedgeLoading] = useState(false);
  const [decisionOpen, setDecisionOpen] = useState(false);
  const [thesisText, setThesisText] = useState("");
  const [savingDecision, setSavingDecision] = useState(false);
  const [exporting, setExporting] = useState<"pdf" | "xlsx" | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isDegraded = dataStatus === "degraded";

  useEffect(() => {
    let cancelled = false;
    getRiskCalibration(marketId)
      .then((result) => {
        if (!cancelled) setCalibration(result);
      })
      .catch(() => {
        if (!cancelled) setCalibration(null);
      });
    return () => {
      cancelled = true;
    };
  }, [marketId, data?.as_of]);

  useEffect(() => {
    if (!data || isDegraded || data.risk_gbp < HEDGE_SUGGESTION_THRESHOLD_GBP) {
      setHedgeSuggestion(null);
      setHedgeLoading(false);
      return;
    }
    let cancelled = false;
    setHedgeLoading(true);
    getOptimalHedge({
      market_code: data.market_code,
      position_gbp: data.position_gbp,
      horizon_hours: data.horizon_hours,
      direction: data.direction === "short" ? "short" : "long",
      target_timestamp: data.target_timestamp,
      n_paths: 500,
    })
      .then((result) => {
        if (!cancelled) setHedgeSuggestion(result);
      })
      .catch(() => {
        if (!cancelled) setHedgeSuggestion(null);
      })
      .finally(() => {
        if (!cancelled) setHedgeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [data?.as_of, data?.risk_gbp, data?.target_timestamp, isDegraded]);

  async function saveDecision() {
    if (!data || thesisText.trim().length === 0) return;
    setSavingDecision(true);
    setDecisionError(null);
    try {
      await createDecision({
        market_code: data.market_code,
        position_gbp: data.position_gbp,
        direction: data.direction === "short" ? "short" : "long",
        horizon_hours: data.horizon_hours,
        risk_gbp: data.risk_gbp,
        likely_gbp: data.likely_gbp,
        upside_gbp: data.upside_gbp,
        thesis_text: thesisText.trim(),
        is_open: true,
      });
      setDecisionOpen(false);
      setThesisText("");
      onDecisionSaved?.();
    } catch (err) {
      setDecisionError(err instanceof Error ? err.message : "decision save failed");
    } finally {
      setSavingDecision(false);
    }
  }

  async function downloadExport(format: "pdf" | "xlsx") {
    if (!data) return;
    setExporting(format);
    setError(null);
    try {
      const blob = await exportRiskAssessment(
        {
          market_code: data.market_code,
          position_gbp: data.position_gbp,
          horizon_hours: data.horizon_hours,
          direction: data.direction === "short" ? "short" : "long",
          target_timestamp: data.target_timestamp,
          n_paths: 500,
        },
        format,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `risk-${data.market_code}-${new Date(data.as_of).toISOString().slice(0, 19).replace(/[:T]/g, "")}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "export failed");
    } finally {
      setExporting(null);
    }
  }

  useEffect(() => {
    if (isDegraded) {
      setData(null);
      setLoading(false);
      setError(null);
      onResult?.(null, false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    let cancelled = false;
    debounceRef.current = setTimeout(() => {
      setLoading(true);
      onResult?.(null, true);
      setError(null);
      const targetTimestamp = cursorTimestampMs ? new Date(cursorTimestampMs).toISOString() : null;
      const request = riskFirst
        ? solveRiskAssessment({
            market_code: marketCode,
            max_risk_gbp: maxRisk,
            horizon_hours: horizon,
            direction,
            position_unit: "GBP",
            target_timestamp: targetTimestamp,
          }).then((res) => {
            if (!cancelled) setPosition(res.resolved_request.position_gbp);
            return res.assessment;
          })
        : runRiskAssessment({
            market_code: marketCode,
            position_gbp: position,
            horizon_hours: horizon,
            direction,
            target_timestamp: targetTimestamp,
          });
      request
        .then((res) => {
          if (!cancelled) {
            setData(res);
            onResult?.(res, false);
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : "assessment failed");
            onResult?.(null, false);
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [marketCode, position, riskFirst, maxRisk, horizon, direction, cursorTimestampMs, isDegraded, onResult]);

  const riskColor = data && data.edge_score > 0.5 ? "text-price-up" : data && data.edge_score < -0.2 ? "text-price-dn" : "text-ink/80";
  const provider = data?.scorer_provider ?? "—";
  const calibrationTone = !calibration
    ? "border-seam bg-bg text-ink/50"
    : calibration.calibration_status === "honest"
      ? "border-price-up/25 bg-price-up/10 text-price-up"
      : calibration.calibration_status === "understating"
        ? "border-price-dn/25 bg-price-dn/10 text-price-dn"
        : "border-amber-400/25 bg-amber-400/10 text-amber-300";
  const calibrationGlyph = calibration?.calibration_status === "honest" ? "✓" : "✗";
  const calibrationStatus = calibration?.calibration_status ?? "collecting data";

  return (
    <div className="rounded-2xl border border-seam bg-surface p-5">
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-ink/40">Position assessment</p>
          <h3 className="mt-1 text-base font-semibold text-ink">Risk · Likely · Upside</h3>
        </div>
        <span
          className={`rounded-md px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider ${
            provider === "gemini" ? "bg-accent/10 text-accent" : "bg-ink/5 text-ink/50"
          }`}
        >
          {isDegraded ? "degraded" : provider === "gemini" ? "AI scoring" : "heuristic"}
        </span>
      </div>

      {/* Position input */}
      <div className="mb-4 space-y-2">
        <div className="flex rounded-lg border border-seam bg-bg p-0.5">
          <button
            type="button"
            onClick={() => setRiskFirst(true)}
            className={`flex-1 rounded px-2 py-1.5 text-[11px] font-mono uppercase tracking-wider transition ${
              riskFirst ? "bg-ink/10 text-ink" : "text-ink/50 hover:text-ink"
            }`}
          >
            Risk-first
          </button>
          <button
            type="button"
            onClick={() => setRiskFirst(false)}
            className={`flex-1 rounded px-2 py-1.5 text-[11px] font-mono uppercase tracking-wider transition ${
              !riskFirst ? "bg-ink/10 text-ink" : "text-ink/50 hover:text-ink"
            }`}
          >
            Notional
          </button>
        </div>
        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">
            {riskFirst ? "Max risk (GBP)" : "Position size (GBP)"}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-lg text-ink/60">£</span>
            <input
              type="number"
              min={100}
              step={100}
              value={riskFirst ? maxRisk : position}
              onChange={(e) => {
                const nextValue = Math.max(100, Number(e.target.value) || 0);
                if (riskFirst) {
                  setMaxRisk(nextValue);
                } else {
                  setPosition(nextValue);
                }
              }}
              className="w-full rounded-lg border border-seam bg-bg px-3 py-2 text-lg font-mono tabular-nums text-ink outline-none focus:border-seam-hi"
            />
          </div>
        </label>
        <div className="flex flex-wrap gap-1.5">
          {(riskFirst ? RISK_PRESETS : PRESETS).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => (riskFirst ? setMaxRisk(p) : setPosition(p))}
              className={`rounded-md px-2 py-1 text-[11px] font-mono transition ${
                (riskFirst ? maxRisk : position) === p
                  ? "bg-ink/10 text-ink"
                  : "bg-bg text-ink/55 hover:bg-ink/5 hover:text-ink"
              }`}
            >
              {p >= 1000 ? `${p / 1000}k` : p}
            </button>
          ))}
        </div>
        {riskFirst ? (
          <div className="flex items-center justify-between rounded-lg border border-seam bg-bg px-3 py-2 text-[11px]">
            <span className="uppercase tracking-widest text-ink/40">Resolved position</span>
            <span className="font-mono tabular-nums text-ink">{formatGbp(position)}</span>
          </div>
        ) : null}
      </div>

      {/* Horizon + direction */}
      <div className="mb-5 grid grid-cols-2 gap-2">
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">Horizon</span>
          <div className="flex rounded-lg border border-seam bg-bg p-0.5">
            {HORIZONS.map((h) => (
              <button
                key={h.value}
                type="button"
                onClick={() => setHorizon(h.value)}
                className={`flex-1 rounded px-1.5 py-1 text-[11px] font-mono transition ${
                  horizon === h.value ? "bg-ink/10 text-ink" : "text-ink/50 hover:text-ink"
                }`}
              >
                {h.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/40">Direction</span>
          <div className="flex rounded-lg border border-seam bg-bg p-0.5">
            {(["long", "short"] as const).map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDirection(d)}
                className={`flex-1 rounded px-1.5 py-1 text-[11px] font-mono uppercase tracking-wider transition ${
                  direction === d
                    ? d === "long"
                      ? "bg-price-up/15 text-price-up"
                      : "bg-price-dn/15 text-price-dn"
                    : "text-ink/50 hover:text-ink"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* The three numbers */}
      {isDegraded ? (
        <div className="rounded-xl border border-price-dn/25 bg-price-dn/10 p-4 text-sm leading-relaxed text-ink/70">
          <p className="font-semibold text-price-dn">Insufficient real data - try refresh.</p>
          <p className="mt-1 text-xs text-ink/50">
            Risk numbers are hidden until this market has a real price source in the selected window.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Risk (95% CVaR)</p>
            <p className="mt-1.5 font-mono text-xl font-semibold tabular-nums text-price-dn">
              {data ? formatGbp(data.risk_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">expected loss in worst 5%</p>
          </div>
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Likely</p>
            <p className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${data && data.likely_gbp >= 0 ? "text-price-up" : "text-price-dn"}`}>
              {data ? formatGbp(data.likely_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">expected P&amp;L</p>
          </div>
          <div className="rounded-xl border border-seam bg-bg p-3">
            <p className="text-[10px] uppercase tracking-widest text-ink/40">Upside</p>
            <p className="mt-1.5 font-mono text-xl font-semibold tabular-nums text-price-up">
              {data ? formatGbp(data.upside_gbp) : "—"}
            </p>
            <p className="mt-1 text-[10px] text-ink/40">95th percentile</p>
          </div>
        </div>
      )}

      <div className={`mt-3 rounded-lg border px-3 py-2 text-[11px] ${calibrationTone}`}>
        <span className="font-semibold">
          Calibration: {calibration ? `${calibrationGlyph} ${calibrationStatus}` : "collecting data"}
        </span>
        <span className="ml-1 text-ink/55">
          {calibration
            ? `(${formatPct(calibration.actual_breach_rate)} breach vs ${formatPct(calibration.claimed_breach_rate)} target, ${calibration.sample_count} reads)`
            : "(0 reads)"}
        </span>
      </div>

      {hedgeSuggestion || hedgeLoading ? (
        <div className="mt-3 rounded-lg border border-accent/25 bg-accent/10 px-3 py-2 text-[11px] text-ink/75">
          <span className="font-semibold text-accent">Suggested hedge:</span>{" "}
          {hedgeSuggestion ? (
            <>
              {direction === "long" ? "short" : "long"} {Math.round(hedgeSuggestion.hedge_ratio * 100)}% notional
              {" → "}risk drops from {formatGbp(hedgeSuggestion.risk_before_gbp)} to{" "}
              {formatGbp(hedgeSuggestion.risk_after_gbp)}, costs {formatGbp(hedgeSuggestion.likely_cost_gbp)} in
              likely P&amp;L.
            </>
          ) : (
            "calculating…"
          )}
        </div>
      ) : null}

      {/* Edge / regime */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Edge</p>
          <p className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${riskColor}`}>
            {data ? data.edge_score.toFixed(2) : "—"}
          </p>
        </div>
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Regime</p>
          <p className="mt-0.5 font-mono text-sm font-semibold uppercase text-ink">
            {data?.regime ?? "—"}
          </p>
        </div>
        <div className="rounded-lg bg-bg p-2">
          <p className="text-[9px] uppercase tracking-widest text-ink/40">Confidence</p>
          <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-ink">
            {data ? `${Math.round(data.confidence * 100)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Rationale */}
      <div className="mt-4 rounded-lg border border-seam bg-bg p-3">
        <p className="text-[10px] uppercase tracking-widest text-ink/40">Read</p>
        <p className="mt-1 text-[12px] leading-relaxed text-ink/75">
          {error ? `Error: ${error}` : data?.rationale ?? (loading ? "scoring…" : "—")}
        </p>
        {data && cursorTimestampMs ? (
          <p className="mt-2 text-[10px] text-ink/40">
            anchored to{" "}
            <span className="font-mono text-ink/55">
              {new Date(cursorTimestampMs).toUTCString().replace("GMT", "UTC")}
            </span>
          </p>
        ) : null}
      </div>

      <button
        type="button"
        disabled={!data || loading || isDegraded}
        onClick={() => {
          setDecisionError(null);
          setDecisionOpen(true);
        }}
        className="mt-3 w-full rounded-lg border border-seam bg-bg px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/70 transition hover:border-seam-hi hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
      >
        Save decision
      </button>

      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["pdf", "xlsx"] as const).map((format) => (
          <button
            key={format}
            type="button"
            disabled={!data || loading || isDegraded || exporting !== null}
            onClick={() => downloadExport(format)}
            className="rounded-lg border border-seam bg-bg px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-ink/70 transition hover:border-seam-hi hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            {exporting === format ? "Exporting…" : `Export ${format}`}
          </button>
        ))}
      </div>

      {decisionOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
          <div className="w-full max-w-lg rounded-xl border border-seam bg-surface p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h3 className="text-sm font-semibold text-ink">Save decision</h3>
              <button
                type="button"
                onClick={() => setDecisionOpen(false)}
                className="rounded-md px-2 py-1 text-sm text-ink/50 hover:bg-bg hover:text-ink"
              >
                ×
              </button>
            </div>
            <textarea
              value={thesisText}
              onChange={(event) => setThesisText(event.target.value)}
              rows={5}
              maxLength={4000}
              placeholder="Thesis"
              className="w-full resize-none rounded-lg border border-seam bg-bg px-3 py-2 text-sm leading-relaxed text-ink outline-none focus:border-seam-hi"
            />
            {decisionError ? <p className="mt-2 text-xs text-price-dn">{decisionError}</p> : null}
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDecisionOpen(false)}
                className="rounded-lg px-3 py-2 text-xs text-ink/55 hover:bg-bg hover:text-ink"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingDecision || thesisText.trim().length === 0}
                onClick={saveDecision}
                className="rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-bg disabled:cursor-not-allowed disabled:opacity-50"
              >
                {savingDecision ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <p className="mt-3 text-[10px] text-ink/30">
        Educational tool. Not financial advice. Numbers reflect modelled distributions, not realised outcomes.
      </p>
    </div>
  );
}

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
const HISTORY_LIMIT = 8;
const HISTORY_STORAGE_PREFIX = "threex.riskHistory.v1";

type SetupMode = "risk-first" | "notional";

type RiskSetup = {
  label: string;
  detail: string;
  mode: SetupMode;
  maxRisk?: number;
  position?: number;
  horizon: number;
  direction: "long" | "short";
};

type RiskHistoryItem = {
  id: string;
  marketCode: string;
  createdAt: string;
  mode: SetupMode;
  maxRisk: number;
  position: number;
  horizon: number;
  direction: "long" | "short";
  riskGbp: number;
  likelyGbp: number;
  upsideGbp: number;
  probLoss: number;
  edgeScore: number;
  gateLabel: string;
};

const COMMON_SETUPS: RiskSetup[] = [
  { label: "Intraday spike", detail: "6h · £500 risk · long", mode: "risk-first", maxRisk: 500, horizon: 6, direction: "long" },
  { label: "Day-ahead base", detail: "24h · £1k risk · long", mode: "risk-first", maxRisk: 1000, horizon: 24, direction: "long" },
  { label: "Fade rally", detail: "12h · £10k notional · short", mode: "notional", position: 10000, horizon: 12, direction: "short" },
  { label: "Stress window", detail: "72h · £2.5k risk · short", mode: "risk-first", maxRisk: 2500, horizon: 72, direction: "short" },
  { label: "Swing book", detail: "48h · £25k notional · long", mode: "notional", position: 25000, horizon: 48, direction: "long" },
];

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

function formatPctValue(value: number, signed = false) {
  const prefix = signed && value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)}%`;
}

function formatCompactTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function historyStorageKey(marketCode: string) {
  return `${HISTORY_STORAGE_PREFIX}.${marketCode}`;
}

function riskMetricLabel(metric: string) {
  if (metric.includes("t5")) return "CVaR95 t(5)";
  if (metric.includes("normal")) return "CVaR95";
  return metric.replaceAll("_", " ");
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
  const [history, setHistory] = useState<RiskHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const historySignatureRef = useRef<string | null>(null);
  const isDegraded = dataStatus === "degraded";

  useEffect(() => {
    historySignatureRef.current = null;
    try {
      const raw = window.localStorage.getItem(historyStorageKey(marketCode));
      setHistory(raw ? (JSON.parse(raw) as RiskHistoryItem[]) : []);
    } catch {
      setHistory([]);
    }
  }, [marketCode]);

  useEffect(() => {
    if (!data || isDegraded) return;
    const signature = [
      data.market_code,
      data.target_timestamp,
      data.position_gbp.toFixed(2),
      data.horizon_hours,
      data.direction,
      data.risk_gbp.toFixed(2),
      data.likely_gbp.toFixed(2),
      data.upside_gbp.toFixed(2),
    ].join("|");
    if (historySignatureRef.current === signature) return;
    historySignatureRef.current = signature;

    const item: RiskHistoryItem = {
      id: signature,
      marketCode: data.market_code,
      createdAt: data.as_of,
      mode: riskFirst ? "risk-first" : "notional",
      maxRisk,
      position: data.position_gbp,
      horizon: data.horizon_hours,
      direction: data.direction === "short" ? "short" : "long",
      riskGbp: data.risk_gbp,
      likelyGbp: data.likely_gbp,
      upsideGbp: data.upside_gbp,
      probLoss: data.prob_loss,
      edgeScore: data.edge_score,
      gateLabel: data.decision_gate?.label ?? "No gate",
    };

    setHistory((current) => {
      const next = [item, ...current.filter((entry) => entry.id !== item.id)].slice(0, HISTORY_LIMIT);
      try {
        window.localStorage.setItem(historyStorageKey(marketCode), JSON.stringify(next));
      } catch {
        // Local storage is a convenience cache; losing it should never block assessment.
      }
      return next;
    });
  }, [data, isDegraded, marketCode, maxRisk, riskFirst]);

  function applySetup(setup: RiskSetup | RiskHistoryItem) {
    const mode = setup.mode;
    setRiskFirst(mode === "risk-first");
    setHorizon(setup.horizon);
    setDirection(setup.direction);
    if (mode === "risk-first") {
      setMaxRisk("maxRisk" in setup && setup.maxRisk ? setup.maxRisk : maxRisk);
      if ("position" in setup && setup.position) setPosition(setup.position);
    } else {
      const nextPosition = "position" in setup && setup.position ? setup.position : position;
      setPosition(nextPosition);
    }
  }

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
  }, [data, isDegraded]);

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
  const gate = data?.decision_gate ?? null;
  const gateTone = !gate
    ? "border-seam bg-bg text-ink/55"
    : gate.action === "clear"
      ? "border-price-up/30 bg-price-up/10 text-price-up"
      : gate.action === "block"
        ? "border-price-dn/30 bg-price-dn/10 text-price-dn"
        : "border-amber-400/30 bg-amber-400/10 text-amber-300";
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

      <HeadlineFigures data={data} loading={loading} isDegraded={isDegraded} />
      <MathSnapshot data={data} loading={loading} isDegraded={isDegraded} />

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

      <div className="mb-4 grid gap-2 2xl:grid-cols-[1fr_1.1fr]">
        <CommonSetups setups={COMMON_SETUPS} onApply={applySetup} />
        <RecentAssessments items={history} onApply={applySetup} />
      </div>

      {gate ? (
        <div className={`mt-3 rounded-xl border p-3 ${gateTone}`}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] uppercase tracking-widest opacity-70">Decision gate</p>
              <p className="mt-1 text-sm font-semibold text-ink">{gate.label}</p>
            </div>
            <div className="text-right">
              <p className="font-mono text-2xl font-semibold tabular-nums text-ink">{gate.score.toFixed(1)}</p>
              <p className="text-[9px] uppercase tracking-widest opacity-60">score</p>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-1.5">
            {gate.checks.slice(0, 4).map((check) => (
              <div key={`${check.label}-${check.value}`} className="rounded-lg bg-bg/70 px-2 py-1.5">
                <p className="truncate text-[9px] uppercase tracking-widest text-ink/35">{check.label}</p>
                <p
                  className={`mt-0.5 truncate font-mono text-[11px] ${
                    check.status === "pass"
                      ? "text-price-up"
                      : check.status === "fail"
                        ? "text-price-dn"
                        : "text-amber-300"
                  }`}
                >
                  {check.value}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-ink/60">{gate.reasons[0]}</p>
        </div>
      ) : null}

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

function HeadlineFigures({
  data,
  loading,
  isDegraded,
}: {
  data: RiskAssessment | null;
  loading: boolean;
  isDegraded: boolean;
}) {
  if (isDegraded) {
    return (
      <div className="-mx-5 mb-4 border-y border-price-dn/25 bg-price-dn/10 px-5 py-4 text-sm leading-relaxed text-ink/70">
        <p className="font-semibold text-price-dn">Insufficient real data - try refresh.</p>
        <p className="mt-1 text-xs text-ink/50">
          Risk numbers are hidden until this market has a real price source in the selected window.
        </p>
      </div>
    );
  }

  return (
    <div className="-mx-5 mb-4 border-y border-seam bg-surface/95 px-5 py-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/40">
          Headline figures
        </span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/35">
          {data ? `${riskMetricLabel(data.risk_metric)} · ${data.n_paths.toLocaleString()} paths` : loading ? "scoring" : "ready"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <FigureCell
          label="Risk"
          value={data ? formatGbp(data.risk_gbp) : "—"}
          helper="worst 5%"
          tone="dn"
          active={loading}
        />
        <FigureCell
          label="Likely"
          value={data ? formatGbp(data.likely_gbp) : "—"}
          helper="mean P&L"
          tone={data && data.likely_gbp < 0 ? "dn" : "up"}
          active={loading}
        />
        <FigureCell
          label="Upside"
          value={data ? formatGbp(data.upside_gbp) : "—"}
          helper="95th pct"
          tone="up"
          active={loading}
        />
      </div>
    </div>
  );
}

function FigureCell({
  label,
  value,
  helper,
  tone,
  active,
}: {
  label: string;
  value: string;
  helper: string;
  tone: "up" | "dn";
  active: boolean;
}) {
  const toneClass = tone === "up" ? "text-price-up" : "text-price-dn";
  return (
    <div className={`min-w-0 rounded-lg border border-seam bg-bg p-3 ${active ? "animate-pulse" : ""}`}>
      <p className="truncate text-[10px] uppercase tracking-widest text-ink/40">{label}</p>
      <p className={`mt-1 truncate font-mono text-xl font-semibold tabular-nums xl:text-2xl ${toneClass}`}>
        {value}
      </p>
      <p className="mt-1 truncate text-[10px] text-ink/40">{helper}</p>
    </div>
  );
}

function MathSnapshot({
  data,
  loading,
  isDegraded,
}: {
  data: RiskAssessment | null;
  loading: boolean;
  isDegraded: boolean;
}) {
  if (isDegraded) return null;

  return (
    <div className="mb-4 rounded-lg border border-seam bg-bg p-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/40">Math tape</span>
        <span className="truncate font-mono text-[10px] uppercase tracking-widest text-ink/35">
          {data ? `P&L = direction × position × Δprice × FX` : loading ? "solving" : "awaiting read"}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 xl:grid-cols-4">
        <MathChip label="P(loss)" value={data ? formatPct(data.prob_loss) : "—"} tone="dn" />
        <MathChip label="σ horizon" value={data ? formatPctValue(data.sigma_return_pct) : "—"} />
        <MathChip
          label="μ horizon"
          value={data ? formatPctValue(data.expected_return_pct, true) : "—"}
          tone={data && data.expected_return_pct < 0 ? "dn" : "up"}
        />
        <MathChip label="VaR95" value={data ? formatGbp(data.var95_gbp) : "—"} tone="dn" />
      </div>
    </div>
  );
}

function MathChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "dn";
}) {
  const toneClass = tone === "up" ? "text-price-up" : tone === "dn" ? "text-price-dn" : "text-ink";
  return (
    <div className="min-w-0 rounded-md border border-seam/70 bg-surface px-2.5 py-2">
      <p className="truncate text-[9px] uppercase tracking-widest text-ink/35">{label}</p>
      <p className={`mt-0.5 truncate font-mono text-sm font-semibold tabular-nums ${toneClass}`}>
        {value}
      </p>
    </div>
  );
}

function CommonSetups({
  setups,
  onApply,
}: {
  setups: RiskSetup[];
  onApply: (setup: RiskSetup) => void;
}) {
  return (
    <div className="rounded-lg border border-seam bg-bg p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-ink/40">Common setups</span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/30">
          {setups.length}
        </span>
      </div>
      <div className="grid gap-1.5">
        {setups.map((setup) => (
          <button
            key={setup.label}
            type="button"
            onClick={() => onApply(setup)}
            className="group rounded-md border border-transparent bg-surface px-2.5 py-2 text-left transition hover:border-seam-hi hover:bg-ink/5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-[12px] font-medium text-ink">{setup.label}</span>
              <span
                className={`shrink-0 font-mono text-[9px] uppercase tracking-widest ${
                  setup.direction === "long" ? "text-price-up" : "text-price-dn"
                }`}
              >
                {setup.direction}
              </span>
            </div>
            <p className="mt-0.5 truncate text-[10px] text-ink/40">{setup.detail}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function RecentAssessments({
  items,
  onApply,
}: {
  items: RiskHistoryItem[];
  onApply: (item: RiskHistoryItem) => void;
}) {
  return (
    <div className="rounded-lg border border-seam bg-bg p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-ink/40">Recent reads</span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/30">
          {items.length}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="rounded-md bg-surface px-3 py-6 text-center text-xs text-ink/40">
          No recent reads yet.
        </div>
      ) : (
        <div className="max-h-56 space-y-1.5 overflow-y-auto pr-1">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onApply(item)}
              className="w-full rounded-md border border-transparent bg-surface px-2.5 py-2 text-left transition hover:border-seam-hi hover:bg-ink/5"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-[10px] uppercase tracking-widest text-ink/35">
                    {formatCompactTime(item.createdAt)} · {item.direction} · {item.horizon}h
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-ink/50">{item.gateLabel}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-mono text-xs font-semibold tabular-nums text-price-dn">
                    {formatGbp(item.riskGbp)}
                  </p>
                  <p
                    className={`mt-0.5 font-mono text-[10px] tabular-nums ${
                      item.likelyGbp >= 0 ? "text-price-up" : "text-price-dn"
                    }`}
                  >
                    {formatGbp(item.likelyGbp)}
                  </p>
                </div>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-1 text-[10px]">
                <span className="truncate text-ink/40">{formatGbp(item.position)}</span>
                <span className="truncate text-ink/40">loss {formatPct(item.probLoss)}</span>
                <span className="truncate text-right font-mono text-ink/45">
                  edge {item.edgeScore.toFixed(2)}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

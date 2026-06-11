"use client";

import { useEffect, useMemo, useState } from "react";

import {
  deleteDecision,
  getDecisions,
  runPortfolioRisk,
  updateDecision,
  type DecisionItem,
  type PortfolioRiskResponse,
} from "@/lib/api";
import { useNearViewport } from "@/lib/use-near-viewport";

function formatGbp(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

function directionOf(item: DecisionItem): "long" | "short" {
  return item.direction === "short" ? "short" : "long";
}

export function PositionBlotter({ refreshKey = 0 }: { refreshKey?: number }) {
  const [items, setItems] = useState<DecisionItem[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioRiskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [portfolioLoading, setPortfolioLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [mutatingId, setMutatingId] = useState<number | null>(null);
  const [localRefresh, setLocalRefresh] = useState(0);
  const { ref: viewportRef, visible } = useNearViewport<HTMLElement>({ rootMargin: "250px" });

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDecisions()
      .then((result) => {
        if (!cancelled) setItems(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "position blotter failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, localRefresh, visible]);

  const openPositions = useMemo(() => items.filter((item) => item.is_open), [items]);

  useEffect(() => {
    if (!visible) {
      return;
    }
    if (openPositions.length === 0) {
      setPortfolio(null);
      setPortfolioError(null);
      setPortfolioLoading(false);
      return;
    }
    let cancelled = false;
    const horizonHours = Math.min(168, Math.max(...openPositions.map((item) => item.horizon_hours), 1));
    setPortfolioLoading(true);
    setPortfolioError(null);
    runPortfolioRisk({
      horizon_hours: horizonHours,
      n_paths: 500,
      positions: openPositions.map((item) => ({
        market_code: item.market_code,
        position_gbp: item.position_gbp,
        direction: directionOf(item),
      })),
    })
      .then((result) => {
        if (!cancelled) setPortfolio(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPortfolio(null);
          setPortfolioError(err instanceof Error ? err.message : "portfolio risk failed");
        }
      })
      .finally(() => {
        if (!cancelled) setPortfolioLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [openPositions, visible]);

  async function closePosition(decisionId: number) {
    setMutatingId(decisionId);
    setError(null);
    try {
      await updateDecision(decisionId, { is_open: false });
      setLocalRefresh((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "position close failed");
    } finally {
      setMutatingId(null);
    }
  }

  async function removePosition(decisionId: number) {
    setMutatingId(decisionId);
    setError(null);
    try {
      await deleteDecision(decisionId);
      setLocalRefresh((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "position delete failed");
    } finally {
      setMutatingId(null);
    }
  }

  return (
    <section ref={viewportRef as React.Ref<HTMLElement>} className="rounded-2xl border border-seam bg-surface p-5">
      <div className="sticky-panel-header -mx-5 -mt-5 mb-3 flex items-baseline justify-between gap-2 rounded-t-2xl bg-surface px-5 pb-3 pt-5">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-ink/45">Position blotter</p>
          <h3 className="mt-1 text-base font-semibold text-ink">Open risk book</h3>
        </div>
        <span className="font-mono text-[10px] tracking-wider text-ink/50">
          {openPositions.length} open
        </span>
      </div>

      {!visible ? <p className="text-sm text-ink/45">Open risk book will load when opened.</p> : null}
      {loading ? <p className="text-sm text-ink/45">Loading positions...</p> : null}
      {error ? <p className="text-sm text-ink/45">Open risk book is temporarily unavailable.</p> : null}
      {visible && !loading && !error && openPositions.length === 0 ? (
        <p className="text-sm text-ink/45">No open positions yet.</p>
      ) : null}

      {openPositions.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-seam bg-bg">
          {openPositions.map((item) => (
            <div key={item.id} className="border-b border-seam p-3 last:border-b-0">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-[11px] uppercase tracking-wider text-ink/55">
                    {item.market_code} · {item.direction} · {item.horizon_hours}h
                  </p>
                  <p className="mt-1 text-sm font-semibold text-ink">{formatGbp(item.position_gbp)}</p>
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    title="Close position"
                    disabled={mutatingId === item.id}
                    onClick={() => closePosition(item.id)}
                    className="rounded-md border border-seam px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-ink/60 transition hover:border-seam-hi hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Close
                  </button>
                  <button
                    type="button"
                    title="Delete position"
                    disabled={mutatingId === item.id}
                    onClick={() => removePosition(item.id)}
                    className="rounded-md border border-seam px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-price-dn/80 transition hover:border-price-dn hover:text-price-dn disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Delete
                  </button>
                </div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                <MetricCell label="Risk" value={formatGbp(item.risk_gbp)} tone="dn" />
                <MetricCell label="Likely" value={formatGbp(item.likely_gbp)} tone={item.likely_gbp >= 0 ? "up" : "dn"} />
                <MetricCell label="Upside" value={formatGbp(item.upside_gbp)} tone="up" />
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {portfolioLoading ? <p className="mt-3 text-xs text-ink/45">Recomputing aggregate...</p> : null}
      {portfolioError ? <p className="mt-3 text-xs text-price-dn">{portfolioError}</p> : null}

      {portfolio ? (
        <div className="mt-4 border-t border-seam pt-4">
          <div className="grid grid-cols-3 gap-2 text-[11px]">
            <MetricCell label="Book risk" value={formatGbp(portfolio.portfolio_risk_gbp)} tone="dn" strong />
            <MetricCell
              label="Book likely"
              value={formatGbp(portfolio.portfolio_likely_gbp)}
              tone={portfolio.portfolio_likely_gbp >= 0 ? "up" : "dn"}
              strong
            />
            <MetricCell label="Book upside" value={formatGbp(portfolio.portfolio_upside_gbp)} tone="up" strong />
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-wider text-ink/40">
            <span>{Math.round(portfolio.prob_loss * 100)}% loss probability</span>
            <span>{formatGbp(portfolio.sum_standalone_risk_gbp)} standalone risk</span>
          </div>
          <div className="mt-3 space-y-1.5">
            {portfolio.contributions.map((item) => (
              <div
                key={`${item.market_code}-${item.direction}-${item.position_gbp}`}
                className="flex items-center justify-between gap-3 text-[11px]"
              >
                <span className="truncate font-mono uppercase tracking-wider text-ink/45">
                  {item.market_code} contribution
                </span>
                <span className="shrink-0 font-mono text-price-dn">{formatGbp(item.risk_contribution_gbp)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function MetricCell({
  label,
  value,
  tone,
  strong = false,
}: {
  label: string;
  value: string;
  tone?: "up" | "dn";
  strong?: boolean;
}) {
  const toneClass = tone === "up" ? "text-price-up" : tone === "dn" ? "text-price-dn" : "text-ink/75";
  return (
    <div className="min-w-0">
      <p className="truncate uppercase tracking-widest text-ink/35">{label}</p>
      <p className={`mt-0.5 truncate font-mono tabular-nums ${toneClass} ${strong ? "text-sm font-semibold" : ""}`}>
        {value}
      </p>
    </div>
  );
}

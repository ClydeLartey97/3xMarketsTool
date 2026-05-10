"use client";

import { useEffect, useState } from "react";

import { getDecisions, type DecisionItem } from "@/lib/api";

function formatGbp(value: number) {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

export function DecisionDiary({
  marketId,
  refreshKey = 0,
}: {
  marketId: number;
  refreshKey?: number;
}) {
  const [items, setItems] = useState<DecisionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDecisions(marketId)
      .then((result) => {
        if (!cancelled) setItems(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "decision diary failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [marketId, refreshKey]);

  return (
    <section className="rounded-2xl border border-seam bg-surface p-5">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-ink/40">Decision diary</p>
          <h3 className="mt-1 text-base font-semibold text-ink">Saved theses</h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink/40">{items.length} reads</span>
      </div>

      {loading ? <p className="text-sm text-ink/45">Loading decisions...</p> : null}
      {error ? <p className="text-sm text-price-dn">{error}</p> : null}
      {!loading && !error && items.length === 0 ? (
        <p className="text-sm text-ink/45">No saved decisions yet.</p>
      ) : null}

      <div className="space-y-2">
        {items.slice(0, 8).map((item) => {
          const matured = item.realized_pnl_gbp !== null;
          return (
            <article key={item.id} className="rounded-xl border border-seam bg-bg p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-mono text-[11px] uppercase tracking-wider text-ink/50">
                  {new Date(item.timestamp).toLocaleString()}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-wider text-ink/50">
                  {item.direction} · {item.horizon_hours}h · {formatGbp(item.position_gbp)}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-ink/80">{item.thesis_text}</p>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <p className="uppercase tracking-widest text-ink/35">Risk</p>
                  <p className="font-mono text-price-dn">{formatGbp(item.risk_gbp)}</p>
                </div>
                <div>
                  <p className="uppercase tracking-widest text-ink/35">Realized</p>
                  <p className={`font-mono ${matured && (item.realized_pnl_gbp ?? 0) >= 0 ? "text-price-up" : "text-price-dn"}`}>
                    {matured ? formatGbp(item.realized_pnl_gbp ?? 0) : "pending"}
                  </p>
                </div>
                <div>
                  <p className="uppercase tracking-widest text-ink/35">Percentile</p>
                  <p className="font-mono text-ink/70">
                    {item.predicted_percentile !== null ? `${item.predicted_percentile.toFixed(1)}p` : "pending"}
                  </p>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

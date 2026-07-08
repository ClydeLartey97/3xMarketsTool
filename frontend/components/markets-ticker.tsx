"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { getMarketsOverview } from "@/lib/api";
import type { Market } from "@/types/domain";

type TickerRow = {
  market: Market;
  spot: number | null;
  prevSpot: number | null;
  changePct: number | null;
};

// Source data only refreshes every ~30 min server-side, so polling faster
// than this just burns proxy invocations and keeps the free-tier backend
// awake for no new information.
const POLL_MS = 300_000;

function formatPrice(value: number, currency: string): string {
  const sym = currency === "GBP" ? "£" : currency === "EUR" ? "€" : "$";
  return `${sym}${value.toFixed(2)}`;
}

export function MarketsTicker({ activeCode }: { activeCode?: string }) {
  const [rows, setRows] = useState<TickerRow[] | null>(null);
  const [pulse, setPulse] = useState(0);
  const lastFetched = useRef(0);

  useEffect(() => {
    let cancelled = false;

    async function load(initial: boolean) {
      if (!initial && document.hidden) return;
      if (Date.now() - lastFetched.current < (initial ? 0 : 30_000)) return;
      lastFetched.current = Date.now();
      try {
        const overview = await getMarketsOverview();
        const filled = overview.map(({ market, spot, previous_spot, change }): TickerRow => ({
          market,
          spot,
          prevSpot: previous_spot,
          changePct:
            change != null && previous_spot != null && previous_spot !== 0
              ? (change / previous_spot) * 100
              : null,
        }));
        if (!cancelled) {
          setRows(filled);
          setPulse((p) => (p + 1) % 1_000_000);
        }
      } catch {
        // soft-fail; ticker stays as-is
      }
    }

    // Catch up when the user returns to a backgrounded tab (polls are
    // skipped while hidden; the 30s floor in load() dedupes rapid toggles).
    function onVisible() {
      if (!document.hidden) load(false);
    }

    load(true);
    const id = window.setInterval(() => load(false), POLL_MS);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const ordered = useMemo(() => {
    if (!rows) return null;
    // Place the active market first; otherwise alphabetical by code.
    const sorted = [...rows].sort((a, b) => a.market.code.localeCompare(b.market.code));
    if (!activeCode) return sorted;
    const idx = sorted.findIndex((r) => r.market.code === activeCode);
    if (idx <= 0) return sorted;
    return [sorted[idx], ...sorted.slice(0, idx), ...sorted.slice(idx + 1)];
  }, [rows, activeCode]);

  if (!ordered) {
    return (
      <div className="flex h-9 w-full items-center overflow-hidden rounded-lg border border-seam bg-bg/60 px-3 text-[11px] text-ink/45">
        Loading markets…
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-seam bg-bg/60">
      <div className="flex h-9 items-stretch divide-x divide-white/5">
        <div className="flex shrink-0 items-center px-3 text-[10px] eyebrow text-ink/40">
          Markets · live
        </div>
        <div className="flex flex-1 items-stretch overflow-x-auto" key={pulse}>
          {ordered.map(({ market, spot, changePct }) => {
            const isActive = market.code === activeCode;
            const dn = changePct != null && changePct < 0;
            const up = changePct != null && changePct > 0;
            const tone = dn ? "text-price-dn" : up ? "text-price-up" : "text-ink/70";
            const arrow = dn ? "▼" : up ? "▲" : "·";
            const status = market.data_status === "degraded" ? "DEGRADED" : null;
            return (
              <Link
                key={market.code}
                href={`/markets/${market.code}` as Route}
                className={`flex min-w-[160px] items-center gap-2 px-3 text-[11px] font-mono transition hover:bg-ink/5 ${
                  isActive ? "bg-ink/10" : ""
                }`}
                title={`${market.name} · ${market.region}`}
              >
                <span className="font-semibold tracking-tight text-ink/90">{market.code}</span>
                <span className={`tabular-nums ${tone}`}>
                  {spot != null
                    ? formatPrice(spot, (market.metadata?.currency as string | undefined) ?? "USD")
                    : "—"}
                </span>
                <span className={`tabular-nums text-[10px] ${tone}`}>
                  {arrow}
                  {changePct != null ? `${Math.abs(changePct).toFixed(2)}%` : "—"}
                </span>
                {status ? (
                  <span className="ml-auto rounded px-1 eyebrow text-[9px] font-semibold text-rose-300">
                    {status}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}

"use client";
/**
 * Radar — proactive cross-market opportunity & threat board.
 *
 * Fetches the ranked scan from `GET /api/radar` and renders two columns:
 * Opportunities (positive, gate-clear edge) and Threats (exposure / negative
 * skew / maturing catalyst, including the user's open book). Each card deep-links
 * into the market workbench. Live refresh is layered on in a later step; for now
 * this fetches once on mount.
 */
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { getRadar, type RadarItem, type RadarResponse } from "@/lib/api";
import { useMarketStream } from "@/lib/use-market-stream";

// Poll floor: refresh even if the live stream is unavailable.
const RADAR_POLL_MS = 60_000;

function fmtGbp(value: number): string {
  const sign = value < 0 ? "−" : "";
  const abs = Math.abs(value);
  if (abs >= 1000) return `${sign}£${Math.round(abs).toLocaleString()}`;
  return `${sign}£${abs.toFixed(0)}`;
}

const CAL_CHIP: Record<string, string> = {
  honest: "bg-price-up/10 text-price-up",
  overstating: "bg-price-hot/10 text-price-hot",
  understating: "bg-price-dn/10 text-price-dn",
  collecting: "bg-ink/5 text-ink/40",
  unknown: "bg-ink/5 text-ink/40",
};

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div>
      <p className="text-[9px] uppercase tracking-widest text-ink/30">{label}</p>
      <p className={`font-mono text-sm font-semibold tabular-nums ${tone}`}>{value}</p>
    </div>
  );
}

function RadarCard({ item }: { item: RadarItem }) {
  return (
    <Link
      href={`/markets/${item.market_code}` as Route}
      className="group block rounded-2xl border border-seam bg-surface p-4 transition-all duration-200 hover:border-seam-hi hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink/30">
              {item.market_code}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-wider ${
                item.direction === "long"
                  ? "bg-price-up/10 text-price-up"
                  : "bg-price-dn/10 text-price-dn"
              }`}
            >
              {item.direction}
            </span>
          </div>
          <h4 className="mt-0.5 text-sm font-semibold leading-tight text-ink">{item.market_name}</h4>
        </div>
        {item.hours_to_catalyst != null ? (
          <span className="shrink-0 rounded-lg bg-price-hot/10 px-2 py-1 font-mono text-[10px] font-medium text-price-hot">
            {item.hours_to_catalyst >= 1
              ? `catalyst ${Math.round(item.hours_to_catalyst)}h`
              : "catalyst now"}
          </span>
        ) : null}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <Stat label="Risk" value={fmtGbp(item.risk_gbp)} tone="text-price-dn" />
        <Stat
          label="Likely"
          value={fmtGbp(item.likely_gbp)}
          tone={item.likely_gbp >= 0 ? "text-price-up" : "text-price-dn"}
        />
        <Stat label="Upside" value={fmtGbp(item.upside_gbp)} tone="text-ink" />
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-seam pt-2.5 text-[11px] text-ink/35">
        <span>
          edge <span className="font-mono text-ink/60">{item.edge_score.toFixed(2)}</span>
        </span>
        <span
          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
            CAL_CHIP[item.calibration_status] ?? CAL_CHIP.unknown
          }`}
        >
          {item.calibration_status}
        </span>
      </div>
      <p className="mt-2 text-[11px] leading-snug text-ink/45">{item.reason}</p>
    </Link>
  );
}

function Column({
  title,
  accent,
  items,
  emptyText,
  loading,
}: {
  title: string;
  accent: string;
  items: RadarItem[];
  emptyText: string;
  loading: boolean;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className={`text-xs font-semibold uppercase tracking-widest ${accent}`}>{title}</h3>
        {!loading ? (
          <span className="font-mono text-[10px] text-ink/30">{items.length}</span>
        ) : null}
      </div>
      {loading ? (
        <div className="flex flex-col gap-3">
          <div className="skeleton h-32 w-full rounded-2xl" />
          <div className="skeleton h-32 w-full rounded-2xl" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-seam bg-surface/40 p-6 text-center text-xs text-ink/35">
          {emptyText}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item) => (
            <RadarCard key={`${item.market_code}-${item.direction}`} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}

export function RadarPanel() {
  const [data, setData] = useState<RadarResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const d = await getRadar();
      if (!mounted.current) return;
      setData(d);
      setError(false);
    } catch {
      if (mounted.current) setError(true);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  // Initial fetch + interval poll floor.
  useEffect(() => {
    mounted.current = true;
    refresh();
    const id = setInterval(refresh, RADAR_POLL_MS);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [refresh]);

  // Live: the worker publishes `radar_updated` on the ALL channel after each scan.
  const { lastMessage } = useMarketStream("ALL");
  useEffect(() => {
    if (lastMessage?.type === "radar_updated") {
      refresh();
    }
  }, [lastMessage, refresh]);

  if (error) {
    return (
      <div className="rounded-2xl border border-seam bg-surface p-6 text-sm text-ink/50">
        The radar is unavailable right now. It will reappear once a scan completes.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-ink/40">
          Ranked across {data?.universe_count ?? "—"} markets
          {data ? ` · ${data.horizon_hours}h horizon` : ""}
        </p>
        {data?.stale ? (
          <span className="rounded-lg bg-ink/5 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-ink/40">
            Computing first scan…
          </span>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Column
          title="Opportunities"
          accent="text-price-up"
          items={data?.opportunities ?? []}
          emptyText="No setups clear the edge + calibration gate right now."
          loading={loading}
        />
        <Column
          title="Threats"
          accent="text-price-dn"
          items={data?.threats ?? []}
          emptyText="All clear — no flagged exposures or maturing catalysts."
          loading={loading}
        />
      </div>
    </div>
  );
}

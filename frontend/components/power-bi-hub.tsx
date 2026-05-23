"use client";

import { useEffect, useState } from "react";

import { PowerBIReport } from "@/components/power-bi-report";
import { getMarkets } from "@/lib/api";
import type { Market } from "@/types/domain";

export function PowerBIHub() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [marketCode, setMarketCode] = useState("");
  const [isLoadingMarkets, setIsLoadingMarkets] = useState(true);
  const [marketError, setMarketError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setIsLoadingMarkets(true);
    setMarketError("");

    getMarkets()
      .then((nextMarkets) => {
        if (cancelled) {
          return;
        }
        setMarkets(nextMarkets);
        setMarketCode((current) => current || nextMarkets[0]?.code || "");
      })
      .catch(() => {
        if (!cancelled) {
          setMarketError("Markets could not be loaded.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingMarkets(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="space-y-5 pb-12">
      <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-ink/35">Embedded analytics</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Power BI workspace</h1>
          </div>
          <label className="flex min-w-[260px] flex-col gap-2">
            <span className="font-mono text-[10px] uppercase tracking-widest text-ink/35">Market filter</span>
            <select
              value={marketCode}
              onChange={(event) => setMarketCode(event.target.value)}
              className="rounded-lg border border-seam bg-bg px-3 py-2 text-sm text-ink outline-none focus:border-seam-hi"
              disabled={isLoadingMarkets || !markets.length}
            >
              {markets.map((market) => (
                <option key={market.code} value={market.code}>
                  {market.name} · {market.region}
                </option>
              ))}
            </select>
            {marketError ? <span className="text-xs text-price-dn">{marketError}</span> : null}
          </label>
        </div>
      </section>

      <PowerBIReport marketCode={marketCode || undefined} />
    </main>
  );
}

import Link from "next/link";
import type { Route } from "next";

import { getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const markets = await getMarkets();

  return (
    <main className="min-h-[calc(100vh-9rem)]">
      <section className="flex min-h-[calc(100vh-9rem)] flex-col justify-between rounded-[2.3rem] border border-white/70 bg-[radial-gradient(circle_at_top_left,_rgba(41,111,95,0.42),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(219,233,241,0.18),_transparent_30%),linear-gradient(135deg,_rgba(7,19,32,0.97)_0%,_rgba(15,31,46,0.96)_50%,_rgba(17,54,74,0.92)_100%)] px-8 py-10 text-white shadow-panel">
        <div className="grid gap-10 xl:grid-cols-[1.2fr_0.8fr] xl:items-end">
          <div className="max-w-4xl">
            <div className="flex items-center gap-4">
              <div className="rounded-[1.35rem] bg-white px-5 py-3 text-4xl font-semibold tracking-tight text-slate shadow-lg">
                3x
              </div>
              <p className="text-xs uppercase tracking-[0.34em] text-white/48">Power market intelligence</p>
            </div>
            <h2 className="mt-8 font-display text-6xl leading-none sm:text-7xl">
              Pick the market.
              <br />
              Enter the desk.
            </h2>
            <p className="mt-6 max-w-2xl text-base leading-8 text-white/74">
              Start with the market you care about, then drop straight into a workbench built around forward price
              formation, structured event shocks, and direct article evidence.
            </p>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/6 p-6 backdrop-blur">
            <p className="text-xs uppercase tracking-[0.28em] text-white/50">Desk focus</p>
            <div className="mt-5 space-y-4 text-sm text-white/74">
              <p>Direct article links instead of generic outlet logos.</p>
              <p>Event-aware forward curve with validation metrics and transparent rationale.</p>
              <p>Desk tools on the chart so users can mark levels, trend lines, and ranges immediately.</p>
            </div>
          </div>
        </div>

        <div className="mt-12 overflow-x-auto pb-3">
          <div className="flex min-w-max gap-5">
            {markets.map((market) => (
              <Link
                key={market.code}
                href={`/markets/${market.code}` as Route}
                className="group w-[330px] rounded-[2rem] border border-white/10 bg-white/8 p-6 backdrop-blur transition hover:-translate-y-1 hover:border-white/25 hover:bg-white/12"
              >
                <p className="text-xs uppercase tracking-[0.24em] text-white/48">{market.region}</p>
                <h3 className="mt-4 text-3xl font-semibold">{market.name}</h3>
                <p className="mt-3 text-sm text-white/65">{market.timezone}</p>
                <div className="mt-6 flex items-center justify-between text-sm text-white/78">
                  <span>{String(market.metadata.market_family ?? market.metadata.launch_tier ?? "Power market")}</span>
                  <span className="rounded-full border border-white/15 px-3 py-1 text-xs uppercase tracking-[0.16em]">
                    Enter
                  </span>
                </div>
              </Link>
            ))}
          </div>
        </div>
        <div className="mt-8 flex flex-wrap gap-3 text-xs uppercase tracking-[0.24em] text-white/45">
          <span>PJM</span>
          <span>ERCOT</span>
          <span>NYISO</span>
          <span>ISO-NE</span>
          <span>Great Britain</span>
          <span>Germany</span>
          <span>France</span>
          <span>Nordics</span>
        </div>
      </section>
    </main>
  );
}

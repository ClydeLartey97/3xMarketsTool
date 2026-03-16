import Link from "next/link";
import type { Route } from "next";

import { getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const markets = await getMarkets();

  return (
    <main className="min-h-[calc(100vh-9rem)]">
      <section className="flex min-h-[calc(100vh-9rem)] flex-col justify-between rounded-[2.3rem] border border-white/70 bg-[linear-gradient(135deg,_rgba(7,19,32,0.96)_0%,_rgba(17,38,56,0.94)_55%,_rgba(17,114,96,0.82)_100%)] px-8 py-10 text-white shadow-panel">
        <div className="max-w-4xl">
          <p className="text-xs uppercase tracking-[0.34em] text-white/55">Market Entry</p>
          <h2 className="mt-4 font-display text-6xl leading-none sm:text-7xl">
            What market do you want
            <br />
            to interrogate?
          </h2>
          <p className="mt-6 max-w-2xl text-base leading-8 text-white/74">
            Start with market selection, then drop directly into a trader-grade workbench with price versus forecast,
            confidence decay, structured event intelligence, and click-through source news from reputable operators,
            regulators, and specialist outlets.
          </p>
        </div>

        <div className="mt-10 overflow-x-auto pb-3">
          <div className="flex min-w-max gap-5">
            {markets.map((market) => (
              <Link
                key={market.code}
                href={`/markets/${market.code}` as Route}
                className="group w-[320px] rounded-[2rem] border border-white/10 bg-white/8 p-6 backdrop-blur transition hover:-translate-y-1 hover:border-white/25 hover:bg-white/12"
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

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 text-sm text-white/78">
            <p className="text-xs uppercase tracking-[0.24em] text-white/42">Coverage</p>
            <p className="mt-3 leading-7">PJM, ERCOT, East Coast U.S. ISOs, Great Britain, Germany, France, and Nordic power.</p>
          </div>
          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 text-sm text-white/78">
            <p className="text-xs uppercase tracking-[0.24em] text-white/42">News Network</p>
            <p className="mt-3 leading-7">20+ reputable sources across wires, exchanges, TSOs, regulators, and specialist energy media.</p>
          </div>
          <div className="rounded-[1.5rem] border border-white/10 bg-white/8 p-5 text-sm text-white/78">
            <p className="text-xs uppercase tracking-[0.24em] text-white/42">Split Screen</p>
            <p className="mt-3 leading-7">Beta feature placeholder is visible in the workbench so the product feels headed toward real desk usage.</p>
          </div>
        </div>
      </section>
    </main>
  );
}

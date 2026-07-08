import { BackendOfflineState } from "@/components/backend-offline-state";
import { MarketCardLive } from "@/components/market-card-live";
import {
  getMarkets,
  getMarketsOverview,
  type MarketOverviewItem,
} from "@/lib/api";

// ISR: the page is served from the CDN and re-rendered at most every
// 5 minutes. Source data only refreshes every ~30 min, so visitors get the
// same content either way — but each visit no longer invokes a server
// function or wakes the free-tier backend/database. (Avoid `force-dynamic`:
// it triggers a Next 16 Turbopack bug in `staticPathsWorker.loadStaticPaths`
// that crashes hydration.)
export const revalidate = 300;

const OVERVIEW_CACHE = { revalidate: 300 } as const;

/**
 * Home page renders the market grid the moment the markets list resolves.
 *
 * Per performance preservation plan §4 the page now fetches a single
 * `/markets/overview` payload server-side, which contains the per-card
 * spot/forecast/24h-avg stats. Each card receives its stats via the
 * `preloaded` prop. If the overview endpoint fails (e.g. older backend),
 * the cards fall back to their legacy per-card /prices + /forecast
 * fetches so the page still works.
 */
export default async function HomePage() {
  try {
    const [markets, overview] = await Promise.all([
      getMarkets(OVERVIEW_CACHE),
      getMarketsOverview(OVERVIEW_CACHE).catch(() => [] as MarketOverviewItem[]),
    ]);
    const overviewByCode = new Map(overview.map((entry) => [entry.market.code, entry]));

    return (
      <main className="animate-fade-in">
        <div className="mb-14 rise max-w-3xl pt-4 sm:pt-10">
          <h1 className="mb-5 font-display text-5xl font-medium leading-[1.08] tracking-[-0.015em] text-ink sm:text-[64px]">
            The power markets,
            <br />
            <span className="italic text-ink/80">read closely.</span>
          </h1>
          <p className="mb-6 max-w-xl text-lg leading-relaxed text-ink/60">
            Live prices, forward curves and event-driven risk across{" "}
            {markets.length} wholesale electricity markets — distilled into three
            numbers you can act on.
          </p>
          <p className="text-sm text-ink/45">
            Built by{" "}
            <a
              href="https://www.linkedin.com/in/clydelartey/"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-ink/70 underline decoration-ink/20 underline-offset-4 transition-colors hover:decoration-accent"
            >
              Clyde Lartey
            </a>{" "}
            ·{" "}
            <a
              href="mailto:clyde.lartey@nyu.edu"
              className="transition-colors hover:text-ink/70"
            >
              clyde.lartey@nyu.edu
            </a>
          </p>
        </div>

        <div className="stagger grid gap-4 sm:grid-cols-2 sm:gap-5 xl:grid-cols-3">
          {markets.map((market) => (
            <MarketCardLive
              key={market.code}
              market={market}
              preloaded={overviewByCode.get(market.code) ?? null}
            />
          ))}
        </div>

        <div className="mt-12 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-ink/25">
          <span>Prices derived from real grid data · Weather via Open-Meteo</span>
          <span>GB prices via ELEXON BMRS · Gas via CME NG=F</span>
          <span>Refreshes every 30 min</span>
        </div>
      </main>
    );
  } catch {
    return <BackendOfflineState title="Start the backend to load markets." />;
  }
}

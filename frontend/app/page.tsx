import { BackendOfflineState } from "@/components/backend-offline-state";
import { MarketCardLive } from "@/components/market-card-live";
import { getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

const REGION_FLAGS: Record<string, string> = {
  Texas: "🇺🇸",
  "U.S. East Coast": "🇺🇸",
  "United Kingdom": "🇬🇧",
  Germany: "🇩🇪",
  France: "🇫🇷",
  Nordics: "🇸🇪",
};

/**
 * Home page renders the market grid the moment the markets list resolves.
 * Each card is a client component that fetches its own spot / forecast
 * after mount, so the home page never blocks on N sequential backend
 * calls before sending HTML.
 */
export default async function HomePage() {
  try {
    const markets = await getMarkets();

    return (
      <main className="animate-fade-in">
        <div className="mb-8">
          <div className="mb-3 flex items-center gap-3">
            <span className="live-dot h-2 w-2 rounded-full bg-accent" />
            <span className="font-mono text-xs uppercase tracking-widest text-accent">
              Live market data
            </span>
          </div>
          <h1 className="mb-2 text-4xl font-bold tracking-tight text-ink">
            Power Market Intelligence
          </h1>
          <p className="max-w-xl text-base text-ink/50">
            Real-time prices, forward curves, and event-driven signals for wholesale electricity
            markets.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {markets.map((market) => (
            <MarketCardLive
              key={market.code}
              market={market}
              flag={REGION_FLAGS[market.region] ?? "🌐"}
            />
          ))}
        </div>

        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-ink/25">
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

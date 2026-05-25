import { BackendOfflineState } from "@/components/backend-offline-state";
import { MarketWorkbench } from "@/components/market-workbench";
import { getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Server-side render is intentionally lean: we only fetch the markets list
 * (one cheap call) to identify the active market by code. The heavier
 * dashboard data is fetched client-side inside the workbench so the hero
 * (the three bubbles) can paint immediately and the rest of the page
 * streams in as data arrives.
 */
export default async function MarketDetailPage({ params }: { params: Promise<{ marketCode: string }> }) {
  try {
    const { marketCode } = await params;
    const markets = await getMarkets();
    const market = markets.find((item) => item.code === marketCode) ?? markets[0];

    return <MarketWorkbench markets={markets} market={market} />;
  } catch {
    return <BackendOfflineState title="Market workbench is waiting for the backend." />;
  }
}

import { MarketWorkbench } from "@/components/market-workbench";
import { getDashboard, getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function MarketDetailPage({ params }: { params: Promise<{ marketCode: string }> }) {
  const { marketCode } = await params;
  const markets = await getMarkets();
  const market = markets.find((item) => item.code === marketCode) ?? markets[0];
  const dashboard = await getDashboard(market.code);

  return <MarketWorkbench markets={markets} dashboard={dashboard} />;
}

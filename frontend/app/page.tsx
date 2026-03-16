import { DashboardExperience } from "@/components/dashboard-experience";
import { getDashboard, getMarkets } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const markets = await getMarkets();
  const initialMarket = markets[0];
  const initialDashboard = await getDashboard(initialMarket.code);

  return <DashboardExperience markets={markets} initialDashboard={initialDashboard} />;
}

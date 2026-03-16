import { DashboardData, EventItem, ForecastPoint, ForecastRunResponse, Market, PricePoint, AlertItem } from "@/types/domain";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed for ${path}`);
  }
  return response.json() as Promise<T>;
}

export function getMarkets(): Promise<Market[]> {
  return fetchJson<Market[]>("/markets");
}

export function getDashboard(marketCode: string): Promise<DashboardData> {
  return fetchJson<DashboardData>(`/dashboard/${marketCode}`);
}

export function getPrices(marketId: number): Promise<PricePoint[]> {
  return fetchJson<PricePoint[]>(`/markets/${marketId}/prices`);
}

export function getForecast(marketId: number): Promise<ForecastPoint[]> {
  return fetchJson<ForecastPoint[]>(`/markets/${marketId}/forecast`);
}

export function getEvents(marketId?: number): Promise<EventItem[]> {
  return fetchJson<EventItem[]>(marketId ? `/markets/${marketId}/events` : "/events");
}

export function getAlerts(marketId: number): Promise<AlertItem[]> {
  return fetchJson<AlertItem[]>(`/markets/${marketId}/alerts`);
}

export function runForecast(marketCode: string): Promise<ForecastRunResponse> {
  return fetchJson<ForecastRunResponse>(`/forecasts/run?market_code=${marketCode}`);
}

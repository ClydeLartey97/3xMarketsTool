import {
  DashboardData,
  EventItem,
  ForecastPoint,
  ForecastRunResponse,
  Market,
  PricePoint,
  AlertItem,
  NewsArticle,
  NewsSource,
} from "@/types/domain";

const PUBLIC_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
const SERVER_API_BASE_URL = process.env.API_INTERNAL_BASE_URL ?? PUBLIC_API_BASE_URL;

function apiBaseUrl(): string {
  return typeof window === "undefined" ? SERVER_API_BASE_URL : PUBLIC_API_BASE_URL;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${apiBaseUrl()}${path}`, { cache: "no-store" });
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

export function getNews(marketId: number): Promise<NewsArticle[]> {
  return fetchJson<NewsArticle[]>(`/markets/${marketId}/news`);
}

export function getNewsSources(): Promise<NewsSource[]> {
  return fetchJson<NewsSource[]>("/news/sources");
}

export function getAlerts(marketId: number): Promise<AlertItem[]> {
  return fetchJson<AlertItem[]>(`/markets/${marketId}/alerts`);
}

export function runForecast(marketCode: string): Promise<ForecastRunResponse> {
  return fetchJson<ForecastRunResponse>(`/forecasts/run?market_code=${marketCode}`);
}

export type RiskAssessment = {
  market_code: string;
  market_name: string;
  as_of: string;
  position_gbp: number;
  direction: "long" | "short";
  horizon_hours: number;
  target_timestamp: string;
  spot_price: number;
  forecast_price: number;
  expected_price: number;
  sigma_price: number;
  sigma_hourly_pct: number;
  expected_return_pct: number;
  sigma_return_pct: number;
  risk_gbp: number;
  likely_gbp: number;
  upside_gbp: number;
  var95_gbp: number;
  edge_score: number;
  confidence: number;
  regime: "calm" | "trending" | "stressed";
  catalyst_severity: number;
  asymmetry: number;
  tail_multiplier: number;
  scorer_provider: string;
  rationale: string;
};

export type RiskAssessmentRequest = {
  market_code: string;
  position_gbp: number;
  horizon_hours: number;
  direction: "long" | "short";
  target_timestamp?: string | null;
};

export async function runRiskAssessment(payload: RiskAssessmentRequest): Promise<RiskAssessment> {
  const response = await fetch(`${apiBaseUrl()}/risk-assessment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`risk-assessment failed: ${response.status}`);
  }
  return response.json() as Promise<RiskAssessment>;
}

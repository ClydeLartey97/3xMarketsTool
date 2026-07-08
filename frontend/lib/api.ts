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
  OptimalHedgeResponse,
  PowerBIEmbedConfig,
  RiskAssessment,
} from "@/types/domain";

export type { OptimalHedgeResponse, RiskAssessment } from "@/types/domain";

const PUBLIC_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/backend";
const SERVER_API_BASE_URL = process.env.API_INTERNAL_BASE_URL ?? "http://127.0.0.1:8000/api";
const TOKEN_STORAGE_KEY = "threex.accessToken";

let cachedServerToken: string | null = null;
let cachedServerTokenExpiresAt = 0;
let pendingServerToken: Promise<string | null> | null = null;

function apiBaseUrl(): string {
  if (typeof window !== "undefined") {
    if (
      PUBLIC_API_BASE_URL.includes("localhost:8000") ||
      PUBLIC_API_BASE_URL.includes("127.0.0.1:8000")
    ) {
      return "/api/backend";
    }
    return PUBLIC_API_BASE_URL;
  }
  return typeof window === "undefined" ? SERVER_API_BASE_URL : PUBLIC_API_BASE_URL;
}

function serverAutoLoginEnabled(): boolean {
  const configured = process.env.SERVER_AUTO_LOGIN;
  if (configured !== undefined) {
    return configured === "true";
  }
  return (
    process.env.NODE_ENV !== "production" ||
    SERVER_API_BASE_URL.includes("127.0.0.1") ||
    SERVER_API_BASE_URL.includes("localhost") ||
    Boolean(process.env.DEMO_USER_PASSWORD)
  );
}

async function getServerAccessToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    return null;
  }
  const staticToken = process.env.API_BEARER_TOKEN;
  if (staticToken) {
    return staticToken;
  }
  if (!serverAutoLoginEnabled()) {
    return null;
  }
  if (cachedServerToken && cachedServerTokenExpiresAt - Date.now() > 60_000) {
    return cachedServerToken;
  }
  if (pendingServerToken) {
    return pendingServerToken;
  }

  pendingServerToken = (async () => {
    const email = process.env.DEMO_USER_EMAIL ?? "demo@3x.local";
    const password =
      process.env.DEMO_USER_PASSWORD ?? (process.env.NODE_ENV === "production" ? "" : "demo-password");
    if (!password) {
      return null;
    }
    try {
      const response = await fetch(`${SERVER_API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        cache: "no-store",
      });
      if (!response.ok) {
        return null;
      }
      const body = (await response.json()) as { access_token: string };
      cachedServerToken = body.access_token;
      cachedServerTokenExpiresAt = Date.now() + 10 * 60 * 1000;
      return cachedServerToken;
    } finally {
      pendingServerToken = null;
    }
  })();

  return pendingServerToken;
}

async function authHeaders(): Promise<Record<string, string>> {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  const token = await getServerAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type CachePolicy = { revalidate?: number };

async function apiFetch(
  path: string,
  init: RequestInit = {},
  cachePolicy: CachePolicy = {},
): Promise<Response> {
  const headers = new Headers(init.headers);
  const auth = await authHeaders();
  for (const [key, value] of Object.entries(auth)) {
    if (!headers.has(key)) {
      headers.set(key, value);
    }
  }
  // A revalidate window opts the request into Next's data cache (used by
  // server components that render statically); everything else stays
  // uncached so interactive reads are always fresh.
  const cacheInit: RequestInit =
    cachePolicy.revalidate != null
      ? { next: { revalidate: cachePolicy.revalidate } }
      : { cache: "no-store" };
  return fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    ...cacheInit,
  });
}

async function fetchJson<T>(path: string, cachePolicy: CachePolicy = {}): Promise<T> {
  const response = await apiFetch(path, {}, cachePolicy);
  if (!response.ok) {
    throw new Error(`API request failed for ${path}`);
  }
  return response.json() as Promise<T>;
}

export function getMarkets(cachePolicy: CachePolicy = {}): Promise<Market[]> {
  return fetchJson<Market[]>("/markets", cachePolicy);
}

export type MarketOverviewForecast = {
  forecast_for_timestamp: string;
  point_estimate: number;
  lower_bound: number;
  upper_bound: number;
  currency: string;
  spike_probability: number;
};

export type MarketOverviewItem = {
  market: Market;
  spot: number | null;
  previous_spot: number | null;
  change: number | null;
  avg_price_24h: number | null;
  spike_probability: number | null;
  next_forecast: MarketOverviewForecast | null;
  data_status: string;
};

export function getMarketsOverview(cachePolicy: CachePolicy = {}): Promise<MarketOverviewItem[]> {
  return fetchJson<MarketOverviewItem[]>("/markets/overview", cachePolicy);
}

export type RadarItem = {
  market_code: string;
  market_name: string;
  direction: string;
  risk_gbp: number;
  likely_gbp: number;
  upside_gbp: number;
  edge_score: number;
  confidence: number;
  regime: string;
  catalyst_severity: number;
  calibration_status: string;
  hours_to_catalyst: number | null;
  radar_score: number;
  kind: "opportunity" | "threat";
  reason: string;
};

export type RadarResponse = {
  generated_at: string;
  horizon_hours: number;
  universe_count: number;
  failed: string[];
  opportunities: RadarItem[];
  threats: RadarItem[];
  stale: boolean;
};

export function getRadar(): Promise<RadarResponse> {
  return fetchJson<RadarResponse>("/radar");
}

export function getDashboard(marketCode: string): Promise<DashboardData> {
  return fetchJson<DashboardData>(`/dashboard/${marketCode}`);
}

export type DashboardSummary = {
  market: Market;
  latest_forecast: ForecastPoint | null;
  forecasts: ForecastPoint[];
  recent_prices: PricePoint[];
  key_metrics: Record<string, number>;
  data_status: string;
};

export function getDashboardSummary(
  marketCode: string,
  historyHours = 168,
): Promise<DashboardSummary> {
  const params = new URLSearchParams({ history_hours: String(historyHours) });
  return fetchJson<DashboardSummary>(`/dashboard/${marketCode}/summary?${params.toString()}`);
}

export function getPrices(marketId: number): Promise<PricePoint[]> {
  return fetchJson<PricePoint[]>(`/markets/${marketId}/prices`);
}

export function getMarketHistory(marketId: number, from?: string, to?: string): Promise<PricePoint[]> {
  const params = new URLSearchParams();
  if (from) {
    params.set("from", from);
  }
  if (to) {
    params.set("to", to);
  }
  const query = params.toString();
  return fetchJson<PricePoint[]>(`/markets/${marketId}/history${query ? `?${query}` : ""}`);
}

export function getMarketTimeseries(
  marketId: number,
  series: string[] = ["demand", "wind", "solar"],
): Promise<MarketTimeseriesPoint[]> {
  return fetchJson<MarketTimeseriesPoint[]>(
    `/markets/${marketId}/timeseries?series=${series.join(",")}`,
  );
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

export function getPowerBIEmbedConfig(marketCode?: string): Promise<PowerBIEmbedConfig> {
  const params = new URLSearchParams();
  if (marketCode) {
    params.set("market_code", marketCode);
  }
  const query = params.toString();
  return fetchJson<PowerBIEmbedConfig>(`/integrations/power-bi/embed-config${query ? `?${query}` : ""}`);
}

export function runForecast(marketCode: string): Promise<ForecastRunResponse> {
  return fetchJson<ForecastRunResponse>(`/forecasts/run?market_code=${marketCode}`);
}

export type RiskAssessmentRequest = {
  market_code: string;
  position_gbp: number;
  horizon_hours: number;
  direction: "long" | "short";
  target_timestamp?: string | null;
  position_unit?: "GBP" | "MWh";
  position_mwh?: number;
  hedge_ratio?: number;
  n_paths?: number;
  path_sample_size?: number;
  preview?: boolean;
  scenarios?: { name: string; sigma_multiplier?: number; drift_shift?: number; spot_shock_pct?: number }[];
};

export type RiskSolveRequest = {
  market_code: string;
  max_risk_gbp: number;
  horizon_hours: number;
  direction: "long" | "short";
  position_unit?: "GBP" | "MWh";
  target_timestamp?: string | null;
};

export type RiskSolveResponse = {
  max_risk_gbp: number;
  achieved_risk_gbp: number;
  risk_error_pct: number;
  tolerance_pct: number;
  iterations: number;
  converged: boolean;
  resolved_request: RiskAssessmentRequest;
  assessment: RiskAssessment;
};

export type SensitivityCoefficient =
  | "tail_multiplier"
  | "asymmetry"
  | "catalyst_severity"
  | "sigma_hourly"
  | "drift_hourly"
  | "fx_to_gbp"
  | "hedge_ratio";

export type RiskSensitivityRequest = RiskAssessmentRequest & {
  coefficients_to_perturb: SensitivityCoefficient[];
};

export type RiskSensitivityCell = {
  perturbation_pct: number;
  risk_gbp: number;
  likely_gbp: number;
  upside_gbp: number;
};

export type RiskSensitivityRow = {
  coefficient: SensitivityCoefficient;
  base_value: number;
  cells: RiskSensitivityCell[];
};

export type RiskSensitivityResponse = {
  market_code: string;
  position_gbp: number;
  direction: string;
  horizon_hours: number;
  perturbations_pct: number[];
  rows: RiskSensitivityRow[];
};

export type RiskCalibration = {
  market_id: number;
  claimed_breach_rate: number;
  actual_breach_rate: number;
  kupiec_p_value: number;
  sample_count: number;
  calibration_status: "honest" | "understating" | "overstating";
};

export type DecisionCreateRequest = {
  market_code: string;
  position_gbp: number;
  direction: "long" | "short";
  horizon_hours: number;
  risk_gbp: number;
  likely_gbp: number;
  upside_gbp: number;
  thesis_text: string;
  is_open?: boolean;
};

export type DecisionUpdateRequest = {
  thesis_text?: string;
  is_open?: boolean;
};

export type DecisionItem = {
  id: number;
  timestamp: string;
  market_id: number;
  market_code: string;
  market_name: string;
  position_gbp: number;
  direction: string;
  horizon_hours: number;
  risk_gbp: number;
  likely_gbp: number;
  upside_gbp: number;
  realized_pnl_gbp: number | null;
  predicted_percentile: number | null;
  thesis_text: string;
  is_open: boolean;
  closed_at: string | null;
};

export type RiskPathFanResponse = {
  market_code: string;
  horizon_hours: number;
  path_hours: number[];
  price_paths: number[][];
  assessment: RiskAssessment;
};

export type MarketTimeseriesPoint = {
  timestamp: string;
  demand_mw: number | null;
  wind_mw: number | null;
  solar_mw: number | null;
  wind_share: number | null;
  solar_share: number | null;
};

export type PortfolioRiskContribution = {
  market_code: string;
  position_gbp: number;
  direction: string;
  standalone_risk_gbp: number;
  standalone_likely_gbp: number;
  standalone_upside_gbp: number;
  simulated_risk_gbp: number;
  risk_contribution_gbp: number;
};

export type PortfolioRiskRequest = {
  positions: { market_code: string; position_gbp: number; direction: "long" | "short" }[];
  horizon_hours?: number;
  n_paths?: number;
};

export type PortfolioRiskResponse = {
  portfolio_risk_gbp: number;
  portfolio_likely_gbp: number;
  portfolio_upside_gbp: number;
  var95_gbp: number;
  prob_loss: number;
  sum_standalone_risk_gbp: number;
  horizon_hours: number;
  n_paths: number;
  correlation_source: string;
  contributions: PortfolioRiskContribution[];
};

export async function runRiskAssessment(
  payload: RiskAssessmentRequest,
  options: { signal?: AbortSignal } = {},
): Promise<RiskAssessment> {
  const response = await apiFetch("/risk-assessment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
      n_paths: payload.n_paths ?? 500,
      preview: payload.preview ?? true,
    }),
    cache: "no-store",
    signal: options.signal,
  });
  if (!response.ok) {
    throw new Error(`risk-assessment failed: ${response.status}`);
  }
  return response.json() as Promise<RiskAssessment>;
}

export async function solveRiskAssessment(payload: RiskSolveRequest): Promise<RiskSolveResponse> {
  const response = await apiFetch("/risk-assessment/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      position_unit: payload.position_unit ?? "GBP",
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`risk-assessment solve failed: ${response.status}`);
  }
  return response.json() as Promise<RiskSolveResponse>;
}

export async function runRiskSensitivity(payload: RiskSensitivityRequest): Promise<RiskSensitivityResponse> {
  const response = await apiFetch("/risk-assessment/sensitivity", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`risk-assessment sensitivity failed: ${response.status}`);
  }
  return response.json() as Promise<RiskSensitivityResponse>;
}

export async function getOptimalHedge(payload: RiskAssessmentRequest): Promise<OptimalHedgeResponse> {
  const response = await apiFetch("/risk-assessment/optimal-hedge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`optimal hedge failed: ${response.status}`);
  }
  return response.json() as Promise<OptimalHedgeResponse>;
}

export function getRiskCalibration(marketId: number): Promise<RiskCalibration> {
  return fetchJson<RiskCalibration>(`/markets/${marketId}/risk-calibration`);
}

export async function createDecision(payload: DecisionCreateRequest): Promise<DecisionItem> {
  const response = await apiFetch("/decisions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`decision save failed: ${response.status}`);
  }
  return response.json() as Promise<DecisionItem>;
}

export function getDecisions(marketId?: number): Promise<DecisionItem[]> {
  const query = marketId ? `?market_id=${marketId}` : "";
  return fetchJson<DecisionItem[]>(`/decisions${query}`);
}

export async function updateDecision(
  decisionId: number,
  payload: DecisionUpdateRequest,
): Promise<DecisionItem> {
  const response = await apiFetch(`/decisions/${decisionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`decision update failed: ${response.status}`);
  }
  return response.json() as Promise<DecisionItem>;
}

export async function deleteDecision(decisionId: number): Promise<{ deleted_id: number }> {
  const response = await apiFetch(`/decisions/${decisionId}`, {
    method: "DELETE",
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`decision delete failed: ${response.status}`);
  }
  return response.json() as Promise<{ deleted_id: number }>;
}

export async function runPortfolioRisk(payload: PortfolioRiskRequest): Promise<PortfolioRiskResponse> {
  const response = await apiFetch("/portfolio-risk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`portfolio risk failed: ${response.status}`);
  }
  return response.json() as Promise<PortfolioRiskResponse>;
}

export async function getRiskPaths(payload: RiskAssessmentRequest): Promise<RiskPathFanResponse> {
  const response = await apiFetch("/risk-assessment/paths", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`risk paths failed: ${response.status}`);
  }
  return response.json() as Promise<RiskPathFanResponse>;
}

export async function exportRiskAssessment(
  payload: RiskAssessmentRequest,
  format: "pdf" | "xlsx",
): Promise<Blob> {
  const response = await apiFetch(`/risk-assessment/export?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      target_timestamp: payload.target_timestamp ?? null,
    }),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`risk export failed: ${response.status}`);
  }
  return response.blob();
}

// E.5 — grid topology + DC-OPF flows for the topology UI.
export type GridBus = {
  name: string;
  load_mw: number;
  gen_mw: number;
  gen_max_mw: number;
  lmp: number;
  is_reference: boolean;
  market_code: string | null;
};

export type GridEdge = {
  from_bus: string;
  to_bus: string;
  flow_mw: number;
  limit_mw: number;
  utilisation: number;
  binding: boolean;
};

export type GridFlowsResponse = {
  buses: GridBus[];
  edges: GridEdge[];
  objective_cost: number;
};

export function getGridFlows(): Promise<GridFlowsResponse> {
  return fetchJson<GridFlowsResponse>("/grid/flows");
}

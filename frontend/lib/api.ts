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
  RiskAssessment,
} from "@/types/domain";

export type { RiskAssessment } from "@/types/domain";

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

export async function solveRiskAssessment(payload: RiskSolveRequest): Promise<RiskSolveResponse> {
  const response = await fetch(`${apiBaseUrl()}/risk-assessment/solve`, {
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
  const response = await fetch(`${apiBaseUrl()}/risk-assessment/sensitivity`, {
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

export function getRiskCalibration(marketId: number): Promise<RiskCalibration> {
  return fetchJson<RiskCalibration>(`/markets/${marketId}/risk-calibration`);
}

export async function createDecision(payload: DecisionCreateRequest): Promise<DecisionItem> {
  const response = await fetch(`${apiBaseUrl()}/decisions`, {
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

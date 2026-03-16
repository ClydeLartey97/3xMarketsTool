export type Market = {
  id: number;
  name: string;
  code: string;
  commodity_type: string;
  region: string;
  timezone: string;
  metadata: Record<string, unknown>;
};

export type PricePoint = {
  id: number;
  market_id: number;
  timestamp: string;
  horizon_type: string;
  price_value: number;
  source: string;
};

export type ForecastPoint = {
  id: number;
  market_id: number;
  forecast_for_timestamp: string;
  generated_at: string;
  point_estimate: number;
  lower_bound: number;
  upper_bound: number;
  spike_probability: number;
  model_version: string;
  rationale_summary: string;
  feature_snapshot_json: Record<string, unknown>;
};

export type EventItem = {
  id: number;
  article_id: number | null;
  market_id: number | null;
  event_type: string;
  title: string;
  description: string;
  affected_region: string;
  asset_type: string;
  capacity_impact_mw: number | null;
  start_time: string | null;
  expected_end_time: string | null;
  severity: string;
  confidence: number;
  price_direction: string;
  estimated_price_impact_pct: number | null;
  rationale: string;
  created_at: string;
};

export type AlertItem = {
  id: number;
  market_id: number;
  alert_type: string;
  title: string;
  body: string;
  severity: string;
  created_at: string;
  is_read: boolean;
};

export type DashboardData = {
  market: Market;
  latest_forecast: ForecastPoint | null;
  forecasts: ForecastPoint[];
  recent_prices: PricePoint[];
  recent_events: EventItem[];
  active_alerts: AlertItem[];
  key_metrics: Record<string, number>;
};

export type ForecastRunResponse = {
  market: Market;
  forecast_points: ForecastPoint[];
  metrics: Record<string, number>;
};

const ENDPOINTS = [
  { method: "GET", path: "/markets", desc: "List all configured markets" },
  { method: "GET", path: "/markets/{id}/prices", desc: "Recent price history (default 168h)" },
  { method: "GET", path: "/markets/{id}/forecast", desc: "Forward curve forecasts (default 48h)" },
  { method: "GET", path: "/markets/{id}/events", desc: "Market-specific structured events" },
  { method: "GET", path: "/markets/{id}/alerts", desc: "Active watchlist alerts" },
  { method: "GET", path: "/dashboard/{code}", desc: "Full dashboard data bundle" },
  { method: "GET", path: "/events", desc: "All structured events across markets" },
  { method: "POST", path: "/forecasts/run", desc: "Trigger forecast run for a market" },
  { method: "POST", path: "/articles/ingest", desc: "Ingest a news article and extract event" },
  { method: "POST", path: "/risk-assessment", desc: "Estimate position risk, likely P&L, and upside" },
  { method: "POST", path: "/markets/{code}/refresh", desc: "Force real-data refresh + cache invalidation" },
  { method: "GET", path: "/health", desc: "Health check with DB status" },
];

const METHOD_STYLE: Record<string, string> = {
  GET: "bg-price-info/10 text-price-info",
  POST: "bg-price-up/10 text-price-up",
};

export default function DeveloperPage() {
  return (
    <main className="animate-fade-in space-y-4">
      {/* Header */}
      <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-ink/35">Developer Surface</p>
        <h1 className="mb-2 text-2xl font-bold tracking-tight text-ink">API Reference</h1>
        <p className="max-w-xl text-sm text-ink/58">
          FastAPI backend at <code className="font-mono text-accent">http://localhost:8000/api</code>.
          Real-time data from EIA, Open-Meteo, ELEXON BMRS, and yfinance — refreshed every 30 minutes.
        </p>
      </div>

      {/* Endpoints */}
      <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <p className="mb-4 font-mono text-[10px] uppercase tracking-widest text-ink/35">Endpoints</p>
        <div className="space-y-1.5">
          {ENDPOINTS.map(({ method, path, desc }) => (
            <div
              key={path + method}
              className="flex items-start gap-3 rounded-xl border border-seam bg-well px-4 py-3"
            >
              <span className={`mt-0.5 shrink-0 rounded px-2 py-0.5 font-mono text-[9px] font-semibold uppercase tracking-widest ${METHOD_STYLE[method] ?? "bg-ink/5 text-ink/45"}`}>
                {method}
              </span>
              <div className="flex-1 min-w-0">
                <code className="font-mono text-sm text-ink/82">{path}</code>
                <p className="mt-0.5 text-xs text-ink/42">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Platform notes */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-ink/35">Data sources</p>
          <div className="space-y-2 text-sm">
            {[
              ["EIA API v2", "US grid demand + wind/solar generation (ERCO, PJM, NYIS, ISNE)"],
              ["Open-Meteo", "Weather: temperature, wind, solar irradiance — no auth required"],
              ["ELEXON BMRS", "GB spot prices via Market Index Data, free public API"],
              ["yfinance NG=F", "Henry Hub natural gas futures for US merit-order pricing"],
              ["yfinance TTF=F", "European TTF gas futures for EU/Nordic markets"],
              ["RSS feeds", "6 energy news sources ingested via feedparser + httpx"],
            ].map(([source, detail]) => (
              <div key={source} className="flex gap-3">
                <span className="mt-0.5 min-w-[100px] shrink-0 font-mono text-[10px] text-accent">{source}</span>
                <span className="text-xs text-ink/48">{detail}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
          <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-ink/35">Architecture</p>
          <div className="space-y-3 text-sm text-ink/58">
            <p>
              Python FastAPI backend owns ingestion, feature engineering, event extraction, price-impact estimation, and
              gradient-boosting forecasting.
            </p>
            <p>
              Forecast cache TTL is 15 minutes — dashboard calls return cached results unless a data refresh has
              invalidated the cache.
            </p>
            <p>
              APScheduler runs a background job every 30 minutes to pull fresh prices across all markets and re-seed
              the SQLite DB.
            </p>
            <div className="mt-4 rounded-xl border border-seam bg-well p-3">
              <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-ink/30">Quickstart</p>
              <pre className="whitespace-pre-wrap font-mono text-xs text-accent">{`cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000`}</pre>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}

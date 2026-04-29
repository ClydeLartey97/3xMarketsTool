import { DashboardData } from "@/types/domain";

function formatSignedImpact(value: number | null | undefined) {
  if (typeof value !== "number") return "Unscored";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

const SEVERITY_STYLES: Record<string, { badge: string; border: string }> = {
  high: { badge: "bg-price-dn/10 text-price-dn", border: "border-price-dn/20" },
  medium: { badge: "bg-price-warn/10 text-price-warn", border: "border-price-warn/20" },
  low: { badge: "bg-ink/5 text-ink/45", border: "border-seam" },
};

export function SignalStack({ dashboard }: { dashboard: DashboardData }) {
  const forwardWindow = dashboard.forecasts.slice(0, 12);
  const baseCase =
    forwardWindow.reduce((sum, p) => sum + p.point_estimate, 0) / Math.max(forwardWindow.length, 1);
  const bullCase = Math.max(
    ...forwardWindow.map((p) => p.upper_bound),
    dashboard.latest_forecast?.upper_bound ?? 0,
  );
  const bearCase = Math.min(
    ...forwardWindow.map((p) => p.lower_bound),
    dashboard.latest_forecast?.lower_bound ?? Infinity,
  );
  const catalysts = dashboard.recent_events.slice(0, 4).map((event) => ({
    id: `event-${event.id}`,
    title: event.title,
    subtitle: `${event.event_type.replaceAll("_", " ")} · ${event.affected_region}`,
    impact: formatSignedImpact(event.estimated_price_impact_pct),
    impactRaw: event.estimated_price_impact_pct,
    confidence: Math.round(event.confidence * 100),
    severity: event.severity,
  }));

  return (
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="mb-4">
        <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">Signal Stack</p>
        <h2 className="text-lg font-semibold text-ink">What would move this market from here?</h2>
      </div>

      {/* Scenario cards */}
      <div className="grid gap-2 sm:grid-cols-3 mb-4">
        <div className="rounded-xl border border-seam bg-well p-4">
          <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-ink/30">Base case</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-ink">${baseCase.toFixed(2)}</p>
          <p className="mt-1 text-xs text-ink/40">12h avg forward price</p>
        </div>
        <div className="rounded-xl border border-price-up/20 bg-price-up/5 p-4">
          <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-price-up/65">Bull stress</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-price-up">${bullCase.toFixed(2)}</p>
          <p className="mt-1 text-xs text-price-up/60">Upper envelope, front strip</p>
        </div>
        <div className="rounded-xl border border-price-hot/20 bg-price-hot/5 p-4">
          <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-price-hot/65">Bear stress</p>
          <p className="font-mono text-2xl font-semibold tabular-nums text-price-hot">${bearCase.toFixed(2)}</p>
          <p className="mt-1 text-xs text-price-hot/60">Lower envelope, front strip</p>
        </div>
      </div>

      {/* Catalyst rows */}
      {catalysts.length > 0 ? (
        <div className="space-y-2">
          <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-ink/30">Catalysts</p>
          {catalysts.map((catalyst) => {
            const style = SEVERITY_STYLES[catalyst.severity] ?? SEVERITY_STYLES.low;
            const impactColor =
              typeof catalyst.impactRaw === "number" && catalyst.impactRaw > 0
                ? "text-price-up"
                : typeof catalyst.impactRaw === "number" && catalyst.impactRaw < 0
                ? "text-price-dn"
                : "text-ink/40";

            return (
              <div
                key={catalyst.id}
                className={`rounded-xl border ${style.border} bg-well p-4`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-sm font-medium text-ink">{catalyst.title}</p>
                    <p className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-ink/32">
                      {catalyst.subtitle}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`font-mono text-sm font-semibold tabular-nums ${impactColor}`}>
                      {catalyst.impact}
                    </span>
                    <span className={`rounded px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest ${style.badge}`}>
                      {catalyst.severity}
                    </span>
                  </div>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-seam">
                    <div
                      className="h-full rounded-full bg-ink/20"
                      style={{ width: `${catalyst.confidence}%` }}
                    />
                  </div>
                  <span className="font-mono text-[10px] text-ink/35">{catalyst.confidence}% conf</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-seam bg-well p-4 text-center">
          <p className="text-sm text-ink/38">No active catalysts · market is in base regime</p>
        </div>
      )}
    </section>
  );
}

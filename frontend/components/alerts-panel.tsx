import { AlertItem } from "@/types/domain";

const SEVERITY_STYLES: Record<string, { badge: string; dot: string }> = {
  high: { badge: "bg-price-dn/10 text-price-dn", dot: "bg-price-dn" },
  medium: { badge: "bg-price-warn/10 text-price-warn", dot: "bg-price-warn" },
  low: { badge: "bg-ink/5 text-ink/45", dot: "bg-ink/25" },
};

export function AlertsPanel({ alerts }: { alerts: AlertItem[] }) {
  return (
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">Alerts</p>
          <h2 className="text-lg font-semibold text-ink">Active watchlist conditions</h2>
        </div>
        {alerts.length > 0 && (
          <span className="font-mono text-xs tabular-nums text-ink/28">{alerts.length} active</span>
        )}
      </div>

      <div className="space-y-2">
        {alerts.length === 0 ? (
          <div className="rounded-xl border border-seam bg-well p-4 text-center">
            <p className="text-sm text-ink/38">No active alerts · watchlist is clear</p>
          </div>
        ) : (
          alerts.map((alert) => {
            const style = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.low;
            return (
              <article key={alert.id} className="rounded-xl border border-seam bg-well p-4">
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${style.dot}`} />
                    <h3 className="text-sm font-semibold text-ink">{alert.title}</h3>
                  </div>
                  <span className={`rounded px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest shrink-0 ${style.badge}`}>
                    {alert.severity}
                  </span>
                </div>
                <p className="text-xs leading-5 text-ink/56">{alert.body}</p>
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

import { AlertItem } from "@/types/domain";

export function AlertsPanel({ alerts }: { alerts: AlertItem[] }) {
  return (
    <section className="rounded-[1.8rem] border border-slate/10 bg-slate p-6 text-white shadow-panel">
      <p className="text-xs uppercase tracking-[0.24em] text-white/55">Alerts</p>
      <h2 className="mt-2 text-2xl font-semibold">Current watchlist conditions</h2>
      <div className="mt-5 space-y-4">
        {alerts.map((alert) => (
          <article key={alert.id} className="rounded-3xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-semibold">{alert.title}</h3>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs uppercase">{alert.severity}</span>
            </div>
            <p className="mt-2 text-sm text-white/70">{alert.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

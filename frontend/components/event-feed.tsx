import { EventItem } from "@/types/domain";

function severityClass(severity: string): string {
  if (severity === "high") return "bg-danger/10 text-danger";
  if (severity === "medium") return "bg-caution/10 text-caution";
  return "bg-slate/10 text-slate";
}

export function EventFeed({ events }: { events: EventItem[] }) {
  return (
    <section className="rounded-[1.8rem] border border-white/60 bg-white/85 p-6 shadow-panel">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.26em] text-slate/60">Structured Events</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate">Latest market-relevant signals</h2>
        </div>
      </div>
      <div className="space-y-4">
        {events.map((event) => (
          <article key={event.id} className="rounded-3xl border border-slate/8 bg-mist/40 p-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${severityClass(event.severity)}`}>
                {event.severity}
              </span>
              <span className="rounded-full bg-slate/5 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate/70">
                {event.event_type.replaceAll("_", " ")}
              </span>
              <span className="text-xs text-slate/55">{new Date(event.created_at).toLocaleString()}</span>
            </div>
            <h3 className="mt-3 text-lg font-semibold text-slate">{event.title}</h3>
            <p className="mt-2 text-sm text-slate/75">{event.description}</p>
            <div className="mt-4 grid gap-3 text-sm text-slate/75 md:grid-cols-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Region</p>
                <p>{event.affected_region}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Impact</p>
                <p>{event.estimated_price_impact_pct ?? 0}%</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Direction</p>
                <p className="capitalize">{event.price_direction}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate/50">Confidence</p>
                <p>{Math.round(event.confidence * 100)}%</p>
              </div>
            </div>
            <p className="mt-3 text-sm italic text-slate/65">{event.rationale}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

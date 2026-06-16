import { prettyEventType } from "@/lib/typography";
import { EventItem } from "@/types/domain";

const SEVERITY_STYLES: Record<string, { badge: string; bar: string }> = {
  high: { badge: "bg-price-dn/10 text-price-dn", bar: "bg-price-dn" },
  medium: { badge: "bg-price-warn/10 text-price-warn", bar: "bg-price-warn" },
  low: { badge: "bg-ink/5 text-ink/45", bar: "bg-ink/20" },
};

const DIRECTION_STYLE: Record<string, string> = {
  up: "text-price-up",
  down: "text-price-dn",
  bullish: "text-price-up",
  bearish: "text-price-dn",
  uncertain: "text-price-warn",
  neutral: "text-ink/40",
};

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function EventFeed({
  events,
  compact = false,
  title = "Latest market-relevant signals",
  subtitle = "Structured Events",
}: {
  events: EventItem[];
  compact?: boolean;
  title?: string;
  subtitle?: string;
}) {
  return (
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="sticky-panel-header -mx-5 -mt-5 mb-4 rounded-t-2xl bg-surface px-5 pb-3 pt-5">
        <p className="mb-1 eyebrow text-[10px] text-ink/45">{subtitle}</p>
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
      </div>

      <div className="space-y-2">
        {events.length === 0 ? (
          <div className="rounded-xl border border-seam bg-well p-4 text-center">
            <p className="text-sm text-ink/38">No events detected · feed is quiet</p>
          </div>
        ) : (
          events.map((event) => {
            const style = SEVERITY_STYLES[event.severity] ?? SEVERITY_STYLES.low;
            const sourceUrl = event.source_url;
            const cardClassName = [
              "rounded-xl border border-seam bg-well p-4",
              sourceUrl ? "group block transition-all hover:border-seam-hi hover:bg-surface" : "",
            ]
              .filter(Boolean)
              .join(" ");
            const content = (
              <>
                {/* Tag row */}
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className={`rounded px-2 py-0.5 eyebrow text-[9px] font-semibold ${style.badge}`}>
                    {event.severity}
                  </span>
                  <span className="rounded bg-ink/5 px-2 py-0.5 text-[10px] text-ink/55">
                    {prettyEventType(event.event_type)}
                  </span>
                  <span className="ml-auto text-[10px] text-ink/45">{formatTime(event.created_at)}</span>
                </div>

                {/* Title */}
                <h3 className="mb-1.5 text-sm font-semibold leading-snug text-ink">{event.title}</h3>

                {/* Description */}
                <p className="text-xs leading-5 text-ink/56">
                  {compact ? `${event.description.slice(0, 140)}…` : event.description}
                </p>

                {/* Stats row */}
                <div className={`mt-3 grid gap-3 text-xs ${compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-4"}`}>
                  <div>
                    <p className="mb-0.5 eyebrow text-[9px] text-ink/30">Region</p>
                    <p className="text-ink/62">{event.affected_region}</p>
                  </div>
                  <div>
                    <p className="mb-0.5 eyebrow text-[9px] text-ink/30">Impact</p>
                    <p className={`font-mono font-semibold tabular-nums ${
                      typeof event.estimated_price_impact_pct !== "number"
                        ? "text-ink/40"
                        : event.estimated_price_impact_pct > 0
                          ? "text-price-up"
                          : event.estimated_price_impact_pct < 0
                            ? "text-price-dn"
                            : "text-ink/40"
                    }`}>
                      {event.estimated_price_impact_pct != null
                        ? `${event.estimated_price_impact_pct > 0 ? "+" : ""}${event.estimated_price_impact_pct}%`
                        : "—"}
                    </p>
                  </div>
                  {!compact && (
                    <>
                      <div>
                        <p className="mb-0.5 eyebrow text-[9px] text-ink/30">Direction</p>
                        <p className={`capitalize ${DIRECTION_STYLE[event.price_direction] ?? "text-ink/40"}`}>
                          {event.price_direction}
                        </p>
                      </div>
                      <div>
                        <p className="mb-0.5 eyebrow text-[9px] text-ink/30">Confidence</p>
                        <div className="flex items-center gap-2">
                          <div className="h-1 flex-1 rounded-full bg-seam">
                            <div
                              className={`h-full rounded-full ${style.bar}`}
                              style={{ width: `${Math.round(event.confidence * 100)}%` }}
                            />
                          </div>
                          <span className="font-mono text-[10px] text-ink/42">
                            {Math.round(event.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    </>
                  )}
                </div>

                {!compact && event.rationale && (
                  <p className="mt-3 border-t border-seam pt-3 text-xs italic text-ink/38">
                    {event.rationale}
                  </p>
                )}

                {!compact && event.analogue_event_ids.length > 0 ? (
                  <p className="mt-2 eyebrow text-[10px] text-ink/32">
                    Analogues #{event.analogue_event_ids.slice(0, 5).join(" #")}
                  </p>
                ) : null}

                {sourceUrl ? (
                  <p className="mt-3 text-right eyebrow text-[10px] text-ink/32 transition-colors group-hover:text-ink/60">
                    Open article →
                  </p>
                ) : null}
              </>
            );

            return sourceUrl ? (
              <a
                key={event.id}
                href={sourceUrl}
                target="_blank"
                rel="noreferrer"
                className={cardClassName}
              >
                {content}
              </a>
            ) : (
              <article key={event.id} className={cardClassName}>
                {content}
              </article>
            );
          })
        )}
      </div>
    </section>
  );
}

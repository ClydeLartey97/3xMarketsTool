import { NewsArticle } from "@/types/domain";

function credibilityColor(rating: number): string {
  if (rating >= 97) return "text-price-up";
  if (rating >= 92) return "text-price-info";
  return "text-price-hot";
}

function formatPublishedTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

const DIRECTION_STYLE: Record<string, string> = {
  up: "text-price-up",
  down: "text-price-dn",
  bullish: "text-price-up",
  bearish: "text-price-dn",
  uncertain: "text-price-warn",
  neutral: "text-ink/40",
};

export function NewsBriefs({ items }: { items: NewsArticle[] }) {
  return (
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">
            Market Intelligence
          </p>
          <h2 className="text-lg font-semibold text-ink">Article-backed evidence</h2>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/25">
          {items.length} articles
        </span>
      </div>

      <div className="space-y-2">
        {items.length === 0 ? (
          <div className="rounded-xl border border-seam bg-well p-4 text-center">
            <p className="text-sm text-ink/38">No articles ingested yet</p>
          </div>
        ) : (
          items.map((item) => (
            <a
              key={item.id}
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              className="group block rounded-xl border border-seam bg-well p-4 transition-all hover:border-seam-hi hover:bg-surface"
            >
              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <span className={`font-mono text-[10px] font-semibold ${credibilityColor(item.credibility_rating)}`}>
                  {item.credibility_rating}/100
                </span>
                <span className="font-mono text-[10px] uppercase tracking-widest text-ink/30">
                  {item.credibility_label}
                </span>
                <span className="font-mono text-[10px] text-ink/22">·</span>
                <span className="font-mono text-[10px] text-ink/40">{item.source_name}</span>
                {item.is_auto_translated && (
                  <span className="rounded bg-price-info/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-price-info">
                    {item.source_language.toUpperCase()} →
                  </span>
                )}
              </div>

              {/* Title */}
              <h3 className="mb-1.5 text-sm font-semibold leading-snug text-ink transition-colors group-hover:text-ink/82">
                {item.display_title}
              </h3>

              {/* Summary */}
              <p className="line-clamp-2 text-xs leading-5 text-ink/56">{item.display_summary}</p>

              {/* Footer */}
              <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-mono uppercase tracking-widest text-ink/28">
                <span>{formatPublishedTime(item.published_at)}</span>
                {item.affected_region && <span>{item.affected_region}</span>}
                {item.event_type && (
                  <span>{item.event_type.replaceAll("_", " ")}</span>
                )}
                {item.price_direction && (
                  <span className={DIRECTION_STYLE[item.price_direction] ?? "text-ink/28"}>
                    {item.price_direction}
                  </span>
                )}
                <span className="ml-auto text-ink/24 transition-colors group-hover:text-ink/42">
                  Open →
                </span>
              </div>
            </a>
          ))
        )}
      </div>
    </section>
  );
}

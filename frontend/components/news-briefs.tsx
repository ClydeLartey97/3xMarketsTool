import { NewsArticle } from "@/types/domain";

function credibilityTone(rating: number): string {
  if (rating >= 97) return "bg-[#e7faf3] text-[#11745c]";
  if (rating >= 92) return "bg-[#eef4fb] text-[#244966]";
  return "bg-[#fff2e6] text-[#b1691f]";
}

export function NewsBriefs({ items }: { items: NewsArticle[] }) {
  return (
    <section className="rounded-[1.8rem] border border-white/70 bg-white/88 p-6 shadow-panel">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.26em] text-slate/60">Structured Market-Moving Developments</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate">News and event context</h2>
        </div>
        <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-3 py-2 text-xs uppercase tracking-[0.18em] text-slate/55">
          Click-through sources
        </div>
      </div>
      <div className="space-y-4">
        {items.map((item) => (
          <a
            key={item.id}
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className="block rounded-[1.4rem] border border-slate/10 bg-[#f7fafc] p-4 transition hover:border-slate/20 hover:bg-white"
          >
            <div className="flex flex-wrap items-center gap-3">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${credibilityTone(item.credibility_rating)}`}>
                Credibility {item.credibility_rating}/100
              </span>
              <span className="rounded-full bg-slate/5 px-3 py-1 text-xs uppercase tracking-[0.16em] text-slate/60">
                {item.credibility_label}
              </span>
              <span className="text-xs text-slate/50">{item.source_name}</span>
              {item.is_auto_translated ? (
                <span className="rounded-full bg-[#f2ecff] px-3 py-1 text-xs text-[#6f4fa2]">
                  Auto-translated from {item.source_language.toUpperCase()}
                </span>
              ) : null}
            </div>
            <h3 className="mt-3 text-lg font-semibold text-slate">{item.display_title}</h3>
            <p className="mt-2 text-sm leading-7 text-slate/74">{item.display_summary}</p>
            <div className="mt-4 flex flex-wrap items-center gap-4 text-xs uppercase tracking-[0.14em] text-slate/48">
              <span>{new Date(item.published_at).toLocaleString()}</span>
              {item.affected_region ? <span>{item.affected_region}</span> : null}
              {item.event_type ? <span>{item.event_type.replaceAll("_", " ")}</span> : null}
              {item.price_direction ? <span>{item.price_direction}</span> : null}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

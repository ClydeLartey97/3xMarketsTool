import { NewsSource } from "@/types/domain";

export function SourceNetwork({ sources }: { sources: NewsSource[] }) {
  return (
    <section className="rounded-[1.8rem] border border-white/70 bg-white/88 p-6 shadow-panel">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.26em] text-slate/60">Reputable Source Network</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate">Curated outlets, exchanges, operators, and regulators</h2>
        </div>
        <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-3 py-2 text-sm text-slate/66">
          {sources.length}+ tracked sources
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sources.map((source) => (
          <a
            key={source.key}
            href={source.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-[1.3rem] border border-slate/10 bg-[#f7fafc] p-4 transition hover:border-slate/20 hover:bg-white"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-base font-semibold text-slate">{source.name}</p>
              <span className="rounded-full bg-slate px-3 py-1 text-xs text-white">{source.credibility_rating}</span>
            </div>
            <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate/50">
              {source.country} · {source.language.toUpperCase()} · {source.credibility_label}
            </p>
            <p className="mt-3 text-sm leading-7 text-slate/73">{source.notes}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

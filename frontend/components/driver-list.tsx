export type DriverEvidence = {
  id: string;
  title: string;
  body: string;
  href?: string;
  sourceName?: string;
  sourceMeta?: string;
};

export function DriverList({
  drivers,
  compact = false,
}: {
  drivers: DriverEvidence[];
  compact?: boolean;
}) {
  return (
    <section className="rounded-[1.8rem] border border-white/60 bg-white/85 p-6 shadow-panel">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Market Drivers</p>
          <h2 className="mt-2 text-2xl font-semibold text-slate">Why the forecast is moving</h2>
        </div>
        <div className="rounded-full border border-slate/10 bg-[#f5f8fb] px-3 py-2 text-xs uppercase tracking-[0.18em] text-slate/55">
          Linked evidence
        </div>
      </div>
      <div className={`mt-5 ${compact ? "space-y-3" : "space-y-3"}`}>
        {drivers.map((driver) => {
          const content = (
            <div
              className={`rounded-2xl border border-slate/8 bg-mist/40 text-slate/80 transition ${
                compact ? "px-4 py-4" : "px-4 py-3"
              } ${driver.href ? "hover:border-slate/16 hover:bg-white" : ""}`}
            >
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate/62">{driver.title}</p>
                {driver.sourceName ? (
                  <span className="rounded-full bg-slate/6 px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-slate/50">
                    {driver.sourceName}
                  </span>
                ) : null}
              </div>
              <p className={`mt-3 text-slate/82 ${compact ? "text-sm leading-7" : "text-sm"}`}>{driver.body}</p>
              {driver.href ? (
                <div className="mt-4 flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.14em] text-slate/50">
                  <span>Open supporting article</span>
                  {driver.sourceMeta ? <span>{driver.sourceMeta}</span> : null}
                </div>
              ) : driver.sourceMeta ? (
                <div className="mt-4 text-xs uppercase tracking-[0.14em] text-slate/50">{driver.sourceMeta}</div>
              ) : null}
            </div>
          );

          if (!driver.href) {
            return <div key={driver.id}>{content}</div>;
          }

          return (
            <a key={driver.id} href={driver.href} target="_blank" rel="noreferrer" className="block">
              {content}
            </a>
          );
        })}
      </div>
    </section>
  );
}

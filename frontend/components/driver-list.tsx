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
    <section className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-ink/35">
            Market Drivers
          </p>
          <h2 className="text-lg font-semibold text-ink">Why the forecast is moving</h2>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/25">
          Linked evidence
        </span>
      </div>

      <div className="space-y-2">
        {drivers.map((driver) => {
          const inner = (
            <div
              className={`rounded-xl border border-seam bg-well p-4 transition-all ${
                driver.href ? "hover:border-seam-hi hover:bg-surface" : ""
              } ${compact ? "" : ""}`}
            >
              <div className="flex flex-wrap items-center gap-2 mb-2">
                <p className="font-mono text-[10px] font-semibold uppercase tracking-widest text-ink/55">
                  {driver.title}
                </p>
                {driver.sourceName && (
                  <span className="rounded bg-ink/5 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-widest text-ink/35">
                    {driver.sourceName}
                  </span>
                )}
              </div>
              <p className="text-sm leading-6 text-ink/62">{driver.body}</p>
              {(driver.href || driver.sourceMeta) && (
                <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-[9px] uppercase tracking-widest text-ink/28">
                  {driver.href && <span className="transition-colors group-hover:text-ink/45">Open article →</span>}
                  {driver.sourceMeta && <span>{driver.sourceMeta}</span>}
                </div>
              )}
            </div>
          );

          if (!driver.href) {
            return <div key={driver.id}>{inner}</div>;
          }

          return (
            <a key={driver.id} href={driver.href} target="_blank" rel="noreferrer" className="group block">
              {inner}
            </a>
          );
        })}
      </div>
    </section>
  );
}

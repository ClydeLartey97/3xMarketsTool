export function DriverList({
  drivers,
  compact = false,
}: {
  drivers: string[];
  compact?: boolean;
}) {
  return (
    <section className="rounded-[1.8rem] border border-white/60 bg-white/85 p-6 shadow-panel">
      <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Market Drivers</p>
      <h2 className="mt-2 text-2xl font-semibold text-slate">Why the forecast is moving</h2>
      <div className={`mt-5 ${compact ? "space-y-3" : "space-y-3"}`}>
        {drivers.map((driver) => (
          <div
            key={driver}
            className={`rounded-2xl border border-slate/8 bg-mist/40 text-slate/80 ${
              compact ? "px-4 py-4 text-sm leading-7" : "px-4 py-3 text-sm"
            }`}
          >
            {driver}
          </div>
        ))}
      </div>
    </section>
  );
}

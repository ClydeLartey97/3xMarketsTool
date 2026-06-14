import { RadarPanel } from "@/components/radar-panel";

export const revalidate = 0;

export default function RadarPage() {
  return (
    <main className="animate-fade-in space-y-4">
      {/* Header */}
      <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
        <div className="mb-3 flex items-center gap-3">
          <span className="font-mono text-xs uppercase tracking-widest text-accent">
            Proactive scan
          </span>
        </div>
        <h1 className="mb-2 text-3xl font-bold tracking-tight text-ink">Radar</h1>
        <p className="max-w-xl text-sm text-ink/55">
          Every market, continuously scored for edge, imminent catalysts, and calibration
          confidence — plus threats against your open book. The setups worth a look,
          surfaced before you go looking.
        </p>
      </div>

      <RadarPanel />
    </main>
  );
}

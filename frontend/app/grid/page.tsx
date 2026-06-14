import { BackendOfflineState } from "@/components/backend-offline-state";
import { GridTopologyView } from "@/components/grid-topology-view";
import { getGridFlows } from "@/lib/api";

export const revalidate = 0;

export default async function GridPage() {
  try {
    const flows = await getGridFlows();
    return (
      <main className="animate-fade-in space-y-4">
        <header className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
          <div className="mb-3 flex items-center gap-3">
            <span className="font-mono text-xs uppercase tracking-widest text-accent">
              Grid topology
            </span>
          </div>
          <h1 className="mb-2 text-3xl font-bold tracking-tight text-ink">
            Inter-zone flows &amp; LMPs
          </h1>
          <p className="max-w-2xl text-sm text-ink/60">
            DC optimal power flow on the canonical 13-bus, 13-line topology
            covering every market we price. Line colour shows utilisation;
            bold red means binding. Bus colour shades by LMP.
          </p>
          <div className="mt-4 flex items-center gap-4 text-[11px] font-mono uppercase tracking-widest text-ink/35">
            <span>{flows.buses.length} buses</span>
            <span>·</span>
            <span>{flows.edges.length} lines</span>
            <span>·</span>
            <span>OPF cost £{flows.objective_cost.toLocaleString()}</span>
          </div>
        </header>
        <GridTopologyView flows={flows} />
      </main>
    );
  } catch {
    return (
      <BackendOfflineState
        title="Grid topology unavailable"
        detail="Could not reach the topology endpoint. The page resumes once the backend is up."
      />
    );
  }
}

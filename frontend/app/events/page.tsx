import { BackendOfflineState } from "@/components/backend-offline-state";
import { EventFeed } from "@/components/event-feed";
import { getEvents } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function EventsPage() {
  try {
    const events = await getEvents();

    return (
      <main className="animate-fade-in space-y-4">
        {/* Header */}
        <div className="rounded-2xl border border-seam bg-surface p-5 shadow-panel">
          <div className="flex items-center gap-3 mb-3">
            <span className="live-dot h-2 w-2 rounded-full bg-accent" />
            <span className="font-mono text-xs uppercase tracking-widest text-accent">
              Live event feed
            </span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-ink mb-2">Event Intelligence</h1>
          <p className="text-ink/55 text-sm max-w-xl">
            Ingested articles and operator signals converted into structured market events —
            typed, regioned, severity-scored, and price-impact estimated.
          </p>
          <div className="mt-4 flex items-center gap-4 text-[11px] font-mono uppercase tracking-widest text-ink/35">
            <span>{events.length} events indexed</span>
            <span>·</span>
            <span>Live refresh every 30 min</span>
          </div>
        </div>

        <EventFeed events={events} title="All market-relevant signals" subtitle="Event Feed" />
      </main>
    );
  } catch {
    return <BackendOfflineState title="Event intelligence needs the API running." />;
  }
}

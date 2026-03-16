import { EventFeed } from "@/components/event-feed";
import { getEvents } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function EventsPage() {
  const events = await getEvents();

  return (
    <main className="space-y-6">
      <section className="rounded-[2rem] border border-white/60 bg-white/85 p-6 shadow-panel">
        <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Event Intelligence</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate">Structured event feed</h2>
        <p className="mt-3 max-w-3xl text-sm text-slate/75">
          The MVP converts seeded articles and operator-style notes into market-aware events with type, region,
          severity, confidence, and estimated price impact rather than presenting loose headlines.
        </p>
      </section>
      <EventFeed events={events} />
    </main>
  );
}

export default function DeveloperPage() {
  return (
    <main className="space-y-6">
      <section className="rounded-[2rem] border border-white/60 bg-white/85 p-6 shadow-panel">
        <p className="text-xs uppercase tracking-[0.24em] text-slate/60">Developer Surface</p>
        <h2 className="mt-2 text-3xl font-semibold text-slate">API and platform notes</h2>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <article className="rounded-3xl border border-slate/10 bg-mist/40 p-4">
            <h3 className="font-semibold text-slate">Core endpoints</h3>
            <p className="mt-2 text-sm text-slate/75">
              <code>GET /markets</code>, <code>GET /markets/{`{market_id}`}/prices</code>,{" "}
              <code>GET /markets/{`{market_id}`}/forecast</code>, <code>GET /events</code>,{" "}
              <code>POST /articles/ingest</code>, <code>POST /forecasts/run</code>.
            </p>
          </article>
          <article className="rounded-3xl border border-slate/10 bg-mist/40 p-4">
            <h3 className="font-semibold text-slate">Platform posture</h3>
            <p className="mt-2 text-sm text-slate/75">
              Python owns ingestion, feature engineering, event extraction, impact estimation, and forecasting so the
              frontend remains a thin institutional dashboard over a reusable analytics engine.
            </p>
          </article>
        </div>
      </section>
    </main>
  );
}

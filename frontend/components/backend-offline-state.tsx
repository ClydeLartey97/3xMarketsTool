type BackendOfflineStateProps = {
  title: string;
  detail?: string;
};

export function BackendOfflineState({
  title,
  detail = "The frontend is running, but it could not reach the Python API at http://localhost:8000/api.",
}: BackendOfflineStateProps) {
  return (
    <main className="min-h-[calc(100vh-9rem)]">
      <section
        className="flex min-h-[calc(100vh-9rem)] flex-col justify-center rounded-[2.3rem] border border-seam px-8 py-10 text-ink shadow-panel"
        style={{
          backgroundImage:
            "radial-gradient(circle at top left, rgb(var(--accent) / 0.14), transparent 24%), linear-gradient(135deg, rgb(var(--surface)) 0%, rgb(var(--well)) 60%, rgb(var(--bg)) 100%)",
        }}
      >
        <div className="max-w-3xl">
          <div className="flex items-center gap-4">
            <div className="rounded-[1.35rem] bg-surface px-5 py-3 text-4xl font-semibold tracking-tight text-ink shadow-panel">
              3x
            </div>
            <p className="text-xs uppercase tracking-[0.34em] text-ink/46">Power market intelligence</p>
          </div>

          <p className="mt-8 text-xs uppercase tracking-[0.28em] text-accent">Backend required</p>
          <h1 className="mt-3 font-display text-5xl leading-none sm:text-6xl">{title}</h1>
          <p className="mt-6 max-w-2xl text-base leading-8 text-ink/70">{detail}</p>

          <div className="mt-8 rounded-[1.8rem] border border-seam bg-surface/85 p-5 backdrop-blur">
            <p className="text-xs uppercase tracking-[0.24em] text-ink/46">Start the backend</p>
            <pre className="mt-4 overflow-x-auto rounded-2xl bg-well px-4 py-4 text-sm leading-7 text-accent">
              <code>{`cd "/Users/clydelartey/Documents/Code/Market Speculation/backend"
python3 -m uvicorn app.main:app --reload --port 8000`}</code>
            </pre>
            <p className="mt-4 text-sm text-ink/62">
              After that, refresh this page. You can check the API directly at `http://localhost:8000/api/health`.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

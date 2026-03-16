type MetricCardProps = {
  label: string;
  value: string;
  tone?: "default" | "positive" | "caution" | "danger";
  helper?: string;
};

const toneMap = {
  default: "from-slate to-ink",
  positive: "from-positive to-[#0a6b54]",
  caution: "from-caution to-[#9a5a05]",
  danger: "from-danger to-[#811f1f]",
};

export function MetricCard({ label, value, tone = "default", helper }: MetricCardProps) {
  return (
    <article className="rounded-[1.6rem] border border-white/60 bg-white/80 p-5 shadow-panel">
      <div className={`mb-5 h-1.5 w-20 rounded-full bg-gradient-to-r ${toneMap[tone]}`} />
      <p className="text-xs uppercase tracking-[0.24em] text-slate/60">{label}</p>
      <p className="mt-3 text-3xl font-semibold text-slate">{value}</p>
      {helper ? <p className="mt-2 text-sm text-slate/70">{helper}</p> : null}
    </article>
  );
}

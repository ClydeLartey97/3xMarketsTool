"use client";

import { useEffect, useState } from "react";

import { getRiskCalibration, type RiskCalibration } from "@/lib/api";

function formatPct(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function CalibrationPanel({ marketId }: { marketId: number }) {
  const [calibration, setCalibration] = useState<RiskCalibration | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRiskCalibration(marketId)
      .then((result) => {
        if (!cancelled) setCalibration(result);
      })
      .catch(() => {
        if (!cancelled) setCalibration(null);
      });
    return () => {
      cancelled = true;
    };
  }, [marketId]);

  const status = calibration?.calibration_status ?? "collecting";
  const tone =
    status === "honest"
      ? "text-price-up"
      : status === "understating"
        ? "text-price-dn"
        : "text-price-warn";

  return (
    <section className="rounded-2xl border border-seam bg-surface p-5">
      <p className="text-[10px] uppercase tracking-widest text-ink/40">Calibration</p>
      <h3 className={`mt-2 text-lg font-semibold ${tone}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </h3>
      <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-lg bg-bg p-3">
          <p className="text-[9px] uppercase tracking-widest text-ink/35">Actual breach</p>
          <p className="mt-1 font-mono text-lg text-ink">
            {calibration ? formatPct(calibration.actual_breach_rate) : "—"}
          </p>
        </div>
        <div className="rounded-lg bg-bg p-3">
          <p className="text-[9px] uppercase tracking-widest text-ink/35">Target</p>
          <p className="mt-1 font-mono text-lg text-ink">
            {calibration ? formatPct(calibration.claimed_breach_rate) : "5.0%"}
          </p>
        </div>
      </div>
      <p className="mt-3 font-mono text-[11px] text-ink/45">
        {calibration ? `${calibration.sample_count} reads · Kupiec p ${calibration.kupiec_p_value.toFixed(3)}` : "0 reads"}
      </p>
    </section>
  );
}

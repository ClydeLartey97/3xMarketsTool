"use client";
/**
 * Compact one-line calibration indicator that sits under the three
 * bubbles. Tells the user whether the model's stated risk band has
 * matched reality on past reads for this market.
 *
 * Distinct from the larger CalibrationPanel — that one stays in the
 * evidence zone for deeper inspection.
 *
 * Loading is derived from the data itself: if no calibration is cached
 * yet, or the cached one is for a different market, we treat the read as
 * still in flight. This keeps us clear of React 19's
 * `set-state-in-effect` rule.
 */
import { useEffect, useState } from "react";

import { getRiskCalibration, type RiskCalibration } from "@/lib/api";

export function CalibrationBadge({ marketId }: { marketId: number }) {
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

  const matchesMarket = calibration !== null && calibration.market_id === marketId;

  if (!matchesMarket) {
    return (
      <div className="inline-flex items-center gap-2 rounded-full border border-seam bg-bg px-3 py-1">
        <span className="h-1.5 w-1.5 rounded-full bg-ink/20" />
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/40">
          Calibration…
        </span>
      </div>
    );
  }

  if (calibration.sample_count < 10) {
    return (
      <div
        title="Calibration tracks whether past risk reads matched realised outcomes. We need at least ~10 matured reads before the indicator is meaningful."
        className="inline-flex items-center gap-2 rounded-full border border-seam bg-bg px-3 py-1"
      >
        <span className="h-1.5 w-1.5 rounded-full bg-ink/30" />
        <span className="font-mono text-[10px] uppercase tracking-widest text-ink/45">
          Calibration · collecting
        </span>
      </div>
    );
  }

  const status = calibration.calibration_status;
  const dotClass =
    status === "honest"
      ? "bg-price-up"
      : status === "overstating"
        ? "bg-price-warn"
        : "bg-price-dn";
  const labelClass =
    status === "honest"
      ? "text-price-up"
      : status === "overstating"
        ? "text-price-warn"
        : "text-price-dn";

  const label =
    status === "honest"
      ? "honest"
      : status === "understating"
        ? "understating risk"
        : "overstating risk";

  return (
    <div
      title={`Actual breach ${(calibration.actual_breach_rate * 100).toFixed(1)}% vs claimed ${(calibration.claimed_breach_rate * 100).toFixed(0)}% over ${calibration.sample_count} matured reads. Kupiec p = ${calibration.kupiec_p_value.toFixed(3)}.`}
      className="inline-flex items-center gap-2 rounded-full border border-seam bg-bg px-3 py-1"
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
      <span className={`font-mono text-[10px] uppercase tracking-widest ${labelClass}`}>
        Calibration · {label}
      </span>
    </div>
  );
}

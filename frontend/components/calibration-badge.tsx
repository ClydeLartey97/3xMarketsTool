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
      <div className="inline-flex items-center gap-2 rounded-full bg-ink/[0.04] px-2.5 py-1">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/25" />
        <span className="eyebrow text-[10px] text-ink/40">
          Calibrating…
        </span>
      </div>
    );
  }

  if (calibration.sample_count < 10) {
    return (
      <div
        title="Calibration tracks whether past risk reads matched realised outcomes. We need at least ~10 matured reads before the indicator is meaningful."
        className="inline-flex items-center gap-2 rounded-full bg-ink/[0.04] px-2.5 py-1"
      >
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink/30" />
        <span className="eyebrow text-[10px] text-ink/45">
          Building calibration
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

  const tintClass =
    status === "honest"
      ? "bg-price-up/10"
      : status === "overstating"
        ? "bg-price-warn/10"
        : "bg-price-dn/10";

  const label =
    status === "honest"
      ? "Calibration honest"
      : status === "understating"
        ? "Understating risk"
        : "Overstating risk";

  return (
    <div
      title={`Actual breach ${(calibration.actual_breach_rate * 100).toFixed(1)}% vs claimed ${(calibration.claimed_breach_rate * 100).toFixed(0)}% over ${calibration.sample_count} matured reads. Kupiec p = ${calibration.kupiec_p_value.toFixed(3)}.`}
      className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 ${tintClass}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
      <span className={`eyebrow text-[10px] ${labelClass}`}>
        {label}
      </span>
    </div>
  );
}

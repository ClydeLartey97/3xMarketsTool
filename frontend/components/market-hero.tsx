"use client";
/**
 * The hero zone: input bar + three bubbles + sticky follow-down strip.
 * This is the first thing a user sees on a market page, and it stays
 * present (in compact form) as they scroll through the evidence beneath.
 *
 * The component owns the assessment state and pushes it back to the
 * parent via `onAssessmentChange` so downstream panels (chart overlay,
 * scenarios, path fan, etc.) can read from the same numbers.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { CalibrationBadge } from "@/components/calibration-badge";
import { RiskBubbles } from "@/components/risk-bubbles";
import { RiskStickyBar } from "@/components/risk-sticky-bar";
import { TradeInputBar, type TradeInputState } from "@/components/trade-input-bar";
import { useRiskAssessment } from "@/lib/use-risk-assessment";
import type { RiskAssessment } from "@/lib/api";

export type MarketHeroProps = {
  marketId: number;
  marketCode: string;
  marketName: string;
  dataStatus?: string;
  cursorTimestampMs?: number | null;
  onAssessmentChange?: (result: { data: RiskAssessment | null; loading: boolean; inputs: TradeInputState }) => void;
};

export function MarketHero({
  marketId,
  marketCode,
  marketName,
  dataStatus = "ready",
  cursorTimestampMs = null,
  onAssessmentChange,
}: MarketHeroProps) {
  const [inputs, setInputs] = useState<TradeInputState>({
    position: 10000,
    direction: "long",
    horizon: 24,
  });
  const [readyMarketCode, setReadyMarketCode] = useState<string | null>(null);
  const [stickyVisible, setStickyVisible] = useState(false);
  const heroRef = useRef<HTMLDivElement | null>(null);
  const inputAnchorRef = useRef<HTMLDivElement | null>(null);

  const isDegraded = dataStatus === "degraded";
  const { data, loading, error } = useRiskAssessment({
    marketCode,
    position: inputs.position,
    direction: inputs.direction,
    horizon: inputs.horizon,
    cursorTimestampMs,
    paused: isDegraded || readyMarketCode !== marketCode,
  });

  // Hand the assessment back up so the parent can drive the evidence zone.
  useEffect(() => {
    onAssessmentChange?.({ data, loading, inputs });
  }, [data, loading, inputs, onAssessmentChange]);

  // Sticky bar visibility — fires once hero exits viewport.
  useEffect(() => {
    if (!heroRef.current || typeof window === "undefined") return;
    const sentinel = heroRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        setStickyVisible(!entry.isIntersecting);
      },
      {
        // Trigger when ~30% of the hero is still visible — feels less abrupt.
        threshold: 0.3,
      },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  const handleEdit = useCallback(() => {
    if (typeof window === "undefined") return;
    window.scrollTo({ top: 0, behavior: "smooth" });
    // After the scroll settles, drop focus into the first input field.
    setTimeout(() => {
      const input = inputAnchorRef.current?.querySelector<HTMLInputElement>("input[type=number]");
      input?.focus();
      input?.select();
    }, 350);
  }, []);

  const handleInputChange = useCallback(
    (next: TradeInputState) => {
      setInputs(next);
      setReadyMarketCode(marketCode);
    },
    [marketCode],
  );

  return (
    <>
      <RiskStickyBar
        visible={stickyVisible}
        data={data}
        loading={loading}
        marketName={marketName}
        marketCode={marketCode}
        onEdit={handleEdit}
      />

      <section ref={heroRef} className="space-y-5">
        <div ref={inputAnchorRef}>
          <TradeInputBar
            marketId={marketId}
            marketCode={marketCode}
            marketName={marketName}
            onChange={handleInputChange}
          />
        </div>

        <div className="relative">
          {isDegraded ? (
            <DegradedNotice />
          ) : (
            <RiskBubbles data={data} loading={loading} error={error} />
          )}
        </div>

        <div className="flex flex-col items-center gap-2">
          <CalibrationBadge marketId={marketId} />
          <p className="max-w-md text-center text-[11px] leading-relaxed text-ink/40">
            Modelled distributions, not realised outcomes. Educational tool — not financial advice.
          </p>
        </div>
      </section>
    </>
  );
}

function DegradedNotice() {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-price-warn/30 bg-price-warn/10 p-6 text-center">
      <p className="eyebrow text-[10px] text-price-warn">Data degraded</p>
      <p className="mt-2 text-sm leading-relaxed text-ink/70">
        This market doesn&apos;t have enough real price data in the selected window to produce a
        trustworthy read. The numbers are hidden until the feed catches up.
      </p>
    </div>
  );
}

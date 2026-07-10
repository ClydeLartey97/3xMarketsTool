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
  const inputAnchorRef = useRef<HTMLDivElement | null>(null);
  const bubblesRef = useRef<HTMLDivElement | null>(null);

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

  // Scroll choreography for the three-number panel:
  //   1. Dissolve — as the page leaves the top the panel eases out (fade +
  //      gentle scale-down + slight lift) rather than just scrolling away.
  //      Driven from one rAF loop off a passive scroll listener; gated
  //      behind prefers-reduced-motion.
  //   2. Hand-off — the sticky side rail appears ONLY once the panel has
  //      scrolled out of view (its bottom edge tucks under the app nav).
  //      This uses an IntersectionObserver rather than the scroll loop so it
  //      is correct on first paint, after restored scroll positions, and in
  //      browsers that throttle rAF — the two states can never show together.
  useEffect(() => {
    const el = bubblesRef.current;
    if (!el || typeof window === "undefined") return;
    const allowMotion = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const START = 40; // grace before the dissolve begins
    const END = 280; // fully dissolved by here
    const NAV = 72; // ~app nav height; the panel counts as gone above this line

    const observer = new IntersectionObserver(
      ([entry]) => {
        const gone = !entry.isIntersecting && entry.boundingClientRect.bottom <= NAV;
        setStickyVisible((prev) => (prev === gone ? prev : gone));
      },
      { rootMargin: `-${NAV}px 0px 0px 0px`, threshold: 0 },
    );
    observer.observe(el);

    let raf = 0;
    const render = () => {
      raf = 0;
      const raw = (window.scrollY - START) / (END - START);
      const p = Math.min(1, Math.max(0, raw));
      // ease-in-out cubic — gentle at both ends.
      const eased = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
      el.style.opacity = String(1 - eased);
      el.style.transform = `translateY(${(-eased * 18).toFixed(2)}px) scale(${(1 - eased * 0.06).toFixed(4)})`;
      el.style.pointerEvents = eased > 0.9 ? "none" : "";
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(render);
    };
    if (allowMotion) {
      render();
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
    }
    return () => {
      observer.disconnect();
      if (allowMotion) {
        window.removeEventListener("scroll", onScroll);
        window.removeEventListener("resize", onScroll);
      }
      if (raf) cancelAnimationFrame(raf);
    };
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

      <section className="space-y-5">
        <div ref={inputAnchorRef}>
          <TradeInputBar
            marketId={marketId}
            marketCode={marketCode}
            marketName={marketName}
            onChange={handleInputChange}
          />
        </div>

        <div
          ref={bubblesRef}
          className="relative"
          style={{ willChange: "transform, opacity", transformOrigin: "center" }}
        >
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

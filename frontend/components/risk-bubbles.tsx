"use client";
/**
 * The three-bubble hero. Risk / Likely / Upside as three large circles —
 * the product's signature mark. The circles use the shared `.orb`
 * treatment (hairline border, faint top-light, soft diffuse lift) so they
 * read as considered objects in both themes; colour is carried only by
 * the numerals (mono, tabular), exactly like the price cards. Numbers
 * animate up on first render and cross-fade on subsequent updates;
 * loading shows a soft pulse.
 */
import { useEffect, useRef, useState } from "react";

import type { RiskAssessment } from "@/lib/api";

export type RiskBubblesProps = {
  data: RiskAssessment | null;
  loading: boolean;
  error?: string | null;
  /** Smaller layout for tight screens / embedded contexts. */
  size?: "lg" | "md";
};

type BubbleTone = "risk" | "likely" | "upside";

const TONE_TEXT: Record<BubbleTone, string> = {
  risk: "text-price-dn",
  likely: "text-ink",
  upside: "text-price-up",
};

const SIZE_CLASSES = {
  lg: {
    bubble: "h-[190px] w-[190px] sm:h-[216px] sm:w-[216px]",
    label: "text-[11px]",
    value: "text-[27px] sm:text-[32px]",
    helper: "text-[10px]",
  },
  md: {
    bubble: "h-[140px] w-[140px]",
    label: "text-[10px]",
    value: "text-xl",
    helper: "text-[9px]",
  },
} as const;

function formatGbp(value: number, signed = false): string {
  const sign = value < 0 ? "-" : signed && value > 0 ? "+" : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
  if (abs >= 10_000) return `${sign}£${(abs / 1000).toFixed(1)}k`;
  if (abs >= 1000) return `${sign}£${(abs / 1000).toFixed(2)}k`;
  return `${sign}£${abs.toFixed(0)}`;
}

/**
 * Lightweight number animation — counts from the previous value to the
 * latest `target` over `ms`. Honours `prefers-reduced-motion`; in that
 * case we skip the animation by scheduling the final value on the next
 * microtask (avoids the React 19 `set-state-in-effect` rule). Effects do
 * not run during SSR, so no server-side branch is needed.
 */
function useAnimatedNumber(target: number, ms = 420): number {
  const [value, setValue] = useState<number>(target);
  const fromRef = useRef<number>(target);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const prefersReduced =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReduced) {
      // Defer to microtask so the setState isn't synchronous-in-effect.
      const id = queueMicrotask(() => {
        setValue(target);
        fromRef.current = target;
      });
      return () => {
        // queueMicrotask isn't cancellable, but the closure's `cancelled`
        // semantics are handled by React naturally — a stale microtask
        // just sets the value to the latest target.
        void id;
      };
    }

    const start = performance.now();
    const from = fromRef.current;
    const cancel = () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
    cancel();

    const step = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      // Ease out cubic for a soft landing.
      const eased = 1 - Math.pow(1 - t, 3);
      const next = from + (target - from) * eased;
      setValue(next);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        rafRef.current = null;
        fromRef.current = target;
      }
    };

    rafRef.current = requestAnimationFrame(step);
    return cancel;
  }, [target, ms]);

  return value;
}

export function RiskBubbles({ data, loading, error, size = "lg" }: RiskBubblesProps) {
  const sizeClasses = SIZE_CLASSES[size];
  const showSkeleton = loading && !data;
  const risk = data?.risk_gbp ?? 0;
  const likely = data?.likely_gbp ?? 0;
  const upside = data?.upside_gbp ?? 0;

  return (
    <div className="flex flex-col items-center gap-6">
      <div className="grid w-full grid-cols-1 place-items-center gap-6 sm:grid-cols-3 sm:gap-8">
        <Bubble
          tone="risk"
          label="Risk"
          helper="Worst 5%"
          rawValue={risk}
          loading={showSkeleton}
          sizeClasses={sizeClasses}
          tooltip="Expected loss in the worst 5% of simulated outcomes."
        />
        <Bubble
          tone="likely"
          label="Likely"
          helper="Expected"
          rawValue={likely}
          signed
          loading={showSkeleton}
          sizeClasses={sizeClasses}
          tooltip="Average outcome across all simulated paths."
        />
        <Bubble
          tone="upside"
          label="Upside"
          helper="Best 5%"
          rawValue={upside}
          signed
          loading={showSkeleton}
          sizeClasses={sizeClasses}
          tooltip="Expected gain in the best 5% of simulated outcomes."
        />
      </div>
      {error ? (
        <p className="rounded-md border border-price-dn/30 bg-price-dn/10 px-3 py-1.5 text-[11px] text-price-dn">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function Bubble({
  tone,
  label,
  helper,
  rawValue,
  signed = false,
  loading,
  sizeClasses,
  tooltip,
}: {
  tone: BubbleTone;
  label: string;
  helper: string;
  rawValue: number;
  signed?: boolean;
  loading: boolean;
  sizeClasses: (typeof SIZE_CLASSES)[keyof typeof SIZE_CLASSES];
  tooltip: string;
}) {
  const animated = useAnimatedNumber(rawValue);
  const display = loading ? "—" : formatGbp(animated, signed);

  return (
    <div
      title={tooltip}
      aria-label={`${label}: ${loading ? "loading" : formatGbp(rawValue, signed)}. ${tooltip}`}
      className={`orb flex flex-col items-center justify-center rounded-full text-center ${
        sizeClasses.bubble
      } ${loading ? "animate-pulse" : ""}`}
    >
      <span className={`mb-1.5 font-medium text-ink/45 ${sizeClasses.label}`}>{label}</span>
      <span className={`font-mono font-semibold tabular-nums ${TONE_TEXT[tone]} ${sizeClasses.value}`}>
        {display}
      </span>
      <span className={`mt-1.5 text-ink/35 ${sizeClasses.helper}`}>{helper}</span>
    </div>
  );
}

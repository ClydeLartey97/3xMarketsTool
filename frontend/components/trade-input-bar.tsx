"use client";
/**
 * The single decision bar at the top of every market page. Position size,
 * direction, horizon — three controls, no more. The bubbles below it
 * recompute as you change anything.
 *
 * On mount, this component will auto-populate from the most recent OPEN
 * decision for the active market (if one exists). Otherwise it falls back
 * to localStorage (last-used values per market). Otherwise it falls back to
 * sensible defaults: £10k long, 24h.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { getDecisions, type DecisionItem } from "@/lib/api";

const HORIZON_OPTIONS = [1, 4, 12, 24, 48];
const POSITION_PRESETS = [1000, 5000, 10000, 25000, 100000];
const STORAGE_PREFIX = "threex.tradeInput.v1";

export type TradeInputState = {
  position: number;
  direction: "long" | "short";
  horizon: number;
};

export type TradeInputBarProps = {
  marketCode: string;
  marketName: string;
  marketId?: number;
  /** Fires whenever inputs settle. Parent uses this to drive the assessment. */
  onChange: (next: TradeInputState) => void;
  /** Optional compact mode for tight layouts. */
  compact?: boolean;
};

const DEFAULT_STATE: TradeInputState = {
  position: 10000,
  direction: "long",
  horizon: 24,
};

function storageKey(marketCode: string) {
  return `${STORAGE_PREFIX}.${marketCode}`;
}

function readStored(marketCode: string): TradeInputState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey(marketCode));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<TradeInputState>;
    if (
      typeof parsed.position === "number" &&
      (parsed.direction === "long" || parsed.direction === "short") &&
      typeof parsed.horizon === "number"
    ) {
      return parsed as TradeInputState;
    }
  } catch {
    /* localStorage is best-effort; ignore parse failures */
  }
  return null;
}

function writeStored(marketCode: string, state: TradeInputState) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(marketCode), JSON.stringify(state));
  } catch {
    /* swallow — quota or private mode */
  }
}

function formatGbpDisplay(value: number) {
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(value);
}

export function TradeInputBar({
  marketCode,
  marketName,
  marketId,
  onChange,
  compact = false,
}: TradeInputBarProps) {
  const [position, setPosition] = useState<number>(DEFAULT_STATE.position);
  const [direction, setDirection] = useState<"long" | "short">(DEFAULT_STATE.direction);
  const [horizon, setHorizon] = useState<number>(DEFAULT_STATE.horizon);
  const [autoPopulated, setAutoPopulated] = useState<"diary" | "storage" | null>(null);
  const [readyMarketCode, setReadyMarketCode] = useState<string | null>(null);
  const userEditedRef = useRef(false);

  // On market change: prefer open diary position, fall back to localStorage,
  // fall back to defaults. We only do this once per market change so the user
  // is free to override.
  useEffect(() => {
    setReadyMarketCode(null);
    userEditedRef.current = false;
    let cancelled = false;

    const stored = readStored(marketCode);
    const initial = stored ?? DEFAULT_STATE;
    setPosition(initial.position);
    setDirection(initial.direction);
    setHorizon(initial.horizon);
    setAutoPopulated(stored ? "storage" : null);
    setReadyMarketCode(marketCode);

    getDecisions(marketId)
      .then((decisions) => {
        if (cancelled || userEditedRef.current) return;
        const openForMarket = decisions
          .filter((d: DecisionItem) => d.is_open && d.market_code === marketCode)
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())[0];
        if (!openForMarket) return;
        const next = {
          position: openForMarket.position_gbp,
          direction: openForMarket.direction === "short" ? "short" : "long",
          horizon: openForMarket.horizon_hours,
        } satisfies TradeInputState;
        if (cancelled) return;
        setPosition(next.position);
        setDirection(next.direction);
        setHorizon(next.horizon);
        setAutoPopulated("diary");
        setReadyMarketCode(marketCode);
      })
      .catch(() => {
        /* The saved-position hint is non-blocking; keep the local/default input. */
      });

    return () => {
      cancelled = true;
    };
  }, [marketCode, marketId]);

  // Persist + propagate on every settle.
  useEffect(() => {
    if (readyMarketCode !== marketCode) return;
    const next: TradeInputState = { position, direction, horizon };
    writeStored(marketCode, next);
    onChange(next);
  }, [marketCode, position, direction, horizon, onChange, readyMarketCode]);

  const sentenceSummary = useMemo(() => {
    const horizonLabel =
      horizon === 1 ? "1 hour" : horizon < 24 ? `${horizon} hours` : `${horizon / 24} day${horizon > 24 ? "s" : ""}`;
    return `£${formatGbpDisplay(position)} ${direction} on ${marketName} held for ${horizonLabel}.`;
  }, [position, direction, horizon, marketName]);

  return (
    <div
      className={`rounded-2xl border border-seam bg-surface ${compact ? "p-3" : "p-4 sm:p-5"} shadow-sm`}
    >
      <div
        className={`grid items-end gap-3 ${compact ? "sm:grid-cols-[1fr_auto_auto]" : "md:grid-cols-[1.4fr_auto_auto]"}`}
      >
        {/* Position size */}
        <label className="block">
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/45">
            Position size
          </span>
          <div className="flex items-center gap-2 rounded-xl border border-seam bg-bg px-3 py-2 focus-within:border-seam-hi">
            <span className="text-xl text-ink/55">£</span>
            <input
              type="number"
              min={100}
              step={100}
              value={position}
              onChange={(e) => {
                userEditedRef.current = true;
                setPosition(Math.max(100, Number(e.target.value) || 0));
              }}
              className="w-full bg-transparent font-mono text-xl font-medium tabular-nums text-ink outline-none"
              aria-label="Position size in GBP"
            />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {POSITION_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                onClick={() => {
                  userEditedRef.current = true;
                  setPosition(preset);
                }}
                className={`rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider transition ${
                  position === preset
                    ? "bg-ink/10 text-ink"
                    : "bg-bg text-ink/45 hover:bg-ink/5 hover:text-ink/80"
                }`}
              >
                £{preset >= 1000 ? `${preset / 1000}k` : preset}
              </button>
            ))}
          </div>
        </label>

        {/* Direction */}
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/45">
            Direction
          </span>
          <div className="flex rounded-xl border border-seam bg-bg p-1">
            {(["long", "short"] as const).map((dir) => {
              const active = direction === dir;
              const tone =
                dir === "long"
                  ? active
                    ? "bg-price-up/15 text-price-up"
                    : "text-ink/45 hover:text-price-up"
                  : active
                    ? "bg-price-dn/15 text-price-dn"
                    : "text-ink/45 hover:text-price-dn";
              return (
                <button
                  key={dir}
                  type="button"
                  onClick={() => {
                    userEditedRef.current = true;
                    setDirection(dir);
                  }}
                  className={`min-w-[64px] rounded-lg px-3 py-2 font-mono text-xs uppercase tracking-wider transition ${tone}`}
                >
                  {dir}
                </button>
              );
            })}
          </div>
        </div>

        {/* Horizon */}
        <div>
          <span className="mb-1 block text-[10px] uppercase tracking-widest text-ink/45">
            Horizon
          </span>
          <div className="flex rounded-xl border border-seam bg-bg p-1">
            {HORIZON_OPTIONS.map((h) => {
              const active = horizon === h;
              return (
                <button
                  key={h}
                  type="button"
                  onClick={() => {
                    userEditedRef.current = true;
                    setHorizon(h);
                  }}
                  className={`min-w-[44px] rounded-lg px-2.5 py-2 font-mono text-xs tabular-nums transition ${
                    active
                      ? "bg-ink/10 text-ink"
                      : "text-ink/45 hover:bg-ink/5 hover:text-ink/80"
                  }`}
                >
                  {h}h
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {!compact ? (
        <p className="mt-3 text-[11px] leading-relaxed text-ink/45">
          {sentenceSummary}{" "}
          {autoPopulated === "diary" ? (
            <span className="rounded-md bg-accent/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent">
              from open diary
            </span>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

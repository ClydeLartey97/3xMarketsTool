"use client";

import { useEffect, useRef, useState } from "react";

import { getPowerBIEmbedConfig } from "@/lib/api";
import type { PowerBIEmbedConfig } from "@/types/domain";

type LoadState = "loading" | "setup" | "embedding" | "ready" | "error";

type EmbeddedReport = {
  on: (eventName: string, handler: (event?: unknown) => void) => void;
  off: (eventName?: string) => void;
};

type PowerBIClientGlobal = {
  factories: {
    hpmFactory: unknown;
    wpmpFactory: unknown;
    routerFactory: unknown;
  };
  models: {
    BackgroundType: { Transparent: unknown };
    FilterType: { Basic: unknown };
    TokenType: { Embed: unknown };
  };
  service: {
    Service: new (hpmFactory: unknown, wpmpFactory: unknown, routerFactory: unknown) => PowerBIServiceLike;
  };
};

type PowerBIServiceLike = {
  embed: (container: HTMLElement, config: Record<string, unknown>) => EmbeddedReport;
  reset: (container: HTMLElement) => void;
};

const POWER_BI_CLIENT_SRC = "https://cdn.jsdelivr.net/npm/powerbi-client@2.23.10/dist/powerbi.min.js";
let powerBIClientPromise: Promise<PowerBIClientGlobal> | null = null;

function canEmbed(config: PowerBIEmbedConfig | null): config is PowerBIEmbedConfig & {
  report_id: string;
  embed_url: string;
  embed_token: string;
} {
  return Boolean(config?.configured && config.report_id && config.embed_url && config.embed_token);
}

function loadPowerBIClient(): Promise<PowerBIClientGlobal> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Power BI client can only load in the browser."));
  }
  const powerBIWindow = window as Window & { powerbi?: PowerBIClientGlobal };
  if (powerBIWindow.powerbi) {
    return Promise.resolve(powerBIWindow.powerbi);
  }
  if (powerBIClientPromise) {
    return powerBIClientPromise;
  }

  powerBIClientPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(`script[src="${POWER_BI_CLIENT_SRC}"]`);
    const script = existing ?? document.createElement("script");
    script.src = POWER_BI_CLIENT_SRC;
    script.async = true;
    script.onload = () => {
      if (powerBIWindow.powerbi) {
        resolve(powerBIWindow.powerbi);
      } else {
        reject(new Error("Power BI client script loaded without a global."));
      }
    };
    script.onerror = () => reject(new Error("Power BI client script failed to load."));
    if (!existing) {
      document.head.appendChild(script);
    }
  });

  return powerBIClientPromise;
}

function buildMarketFilters(powerbi: PowerBIClientGlobal, config: PowerBIEmbedConfig) {
  if (!config.market_code || !config.filter_table || !config.filter_column) {
    return [];
  }

  return [
    {
      $schema: "http://powerbi.com/product/schema#basic",
      target: {
        table: config.filter_table,
        column: config.filter_column,
      },
      operator: "In",
      values: [config.market_code],
      filterType: powerbi.models.FilterType.Basic,
      requireSingleSelection: true,
    },
  ];
}

export function PowerBIReport({
  marketCode,
  compact = false,
}: {
  marketCode?: string;
  compact?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [config, setConfig] = useState<PowerBIEmbedConfig | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setMessage("");
    setConfig(null);

    getPowerBIEmbedConfig(marketCode)
      .then((nextConfig) => {
        if (cancelled) {
          return;
        }
        setConfig(nextConfig);
        setState(nextConfig.configured ? "embedding" : "setup");
        setMessage(nextConfig.reason ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setState("error");
          setMessage("Power BI configuration could not be loaded.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [marketCode]);

  useEffect(() => {
    if (!canEmbed(config) || !containerRef.current) {
      return;
    }

    const container = containerRef.current;
    let disposed = false;
    let powerBIService: PowerBIServiceLike | null = null;

    loadPowerBIClient()
      .then((powerbi) => {
        if (disposed) {
          return;
        }

        powerBIService = new powerbi.service.Service(
          powerbi.factories.hpmFactory,
          powerbi.factories.wpmpFactory,
          powerbi.factories.routerFactory,
        );

        const embedConfig: Record<string, unknown> = {
          type: "report",
          id: config.report_id,
          embedUrl: config.embed_url,
          accessToken: config.embed_token,
          tokenType: powerbi.models.TokenType.Embed,
          pageName: config.page_name ?? undefined,
          filters: buildMarketFilters(powerbi, config),
          settings: {
            background: powerbi.models.BackgroundType.Transparent,
            panes: {
              filters: {
                expanded: false,
                visible: false,
              },
              pageNavigation: {
                visible: true,
              },
            },
          },
        };

        const report = powerBIService.embed(container, embedConfig);
        report.off("loaded");
        report.off("error");
        report.on("loaded", () => {
          if (!disposed) {
            setState("ready");
          }
        });
        report.on("error", () => {
          if (!disposed) {
            setState("error");
            setMessage("Power BI report failed to render.");
          }
        });
      })
      .catch(() => {
        if (!disposed) {
          setState("error");
          setMessage("Power BI client script could not be loaded.");
        }
      });

    return () => {
      disposed = true;
      if (powerBIService) {
        powerBIService.reset(container);
      }
    };
  }, [config]);

  const heightClass = compact ? "h-[520px]" : "h-[680px]";
  const setupHeightClass = compact ? "min-h-[120px]" : "min-h-[260px]";
  const setupMessage = compact
    ? "Optional analytics are not connected for this local run."
    : "Power BI is optional here. Add the Power BI environment variables when you want to connect a real embedded report.";

  return (
    <section className="rounded-2xl border border-seam bg-surface p-4 shadow-panel sm:p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-ink/35">Power BI</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-ink">
            {config?.report_name ?? "Embedded analytics"}
          </h2>
        </div>
        <span className="rounded-lg border border-seam bg-bg px-3 py-1.5 font-mono text-[10px] uppercase tracking-widest text-ink/45">
          {marketCode ?? "All markets"}
        </span>
      </div>

      {state === "setup" ? (
        <div className={`${setupHeightClass} flex items-center justify-center rounded-xl border border-dashed border-seam bg-well p-6`}>
          <div className="max-w-xl text-center">
            <p className="text-sm font-semibold text-ink">Power BI not connected</p>
            <p className="mt-2 text-sm leading-6 text-ink/55">{setupMessage}</p>
          </div>
        </div>
      ) : state === "error" ? (
        <div className={`${heightClass} flex items-center justify-center rounded-xl border border-seam bg-well p-6`}>
          <div className="max-w-xl text-center">
            <p className="text-sm font-semibold text-price-dn">Power BI unavailable</p>
            <p className="mt-2 text-sm leading-6 text-ink/55">{message}</p>
          </div>
        </div>
      ) : (
        <div className="relative overflow-hidden rounded-xl border border-seam bg-well">
          {state !== "ready" ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/82 text-sm text-ink/45">
              Loading Power BI...
            </div>
          ) : null}
          <div ref={containerRef} className={`${heightClass} w-full`} />
        </div>
      )}
    </section>
  );
}

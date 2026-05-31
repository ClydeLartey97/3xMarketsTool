"use client";

import { useEffect, useMemo, useState } from "react";

const PUBLIC_WS_BASE_URL = process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://127.0.0.1:8000";

export type MarketStreamMessage =
  | {
      type: "price_tick";
      market_code: string;
      timestamp: string;
      price_value: number;
      currency?: string;
      source?: string;
    }
  | {
      type: "forecast_revision" | "new_event" | "alert" | "risk_recomputed" | "connected";
      market_code?: string;
      [key: string]: unknown;
    };

function marketWebSocketUrl(marketCode: string): string {
  const url = new URL(PUBLIC_WS_BASE_URL);
  if (url.protocol === "http:") {
    url.protocol = "ws:";
  } else if (url.protocol === "https:") {
    url.protocol = "wss:";
  }
  url.pathname = `/ws/markets/${encodeURIComponent(marketCode)}`;
  url.search = "";
  return url.toString();
}

export function useMarketStream(marketCode: string) {
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [lastMessage, setLastMessage] = useState<MarketStreamMessage | null>(null);
  const [priceTick, setPriceTick] = useState<Extract<MarketStreamMessage, { type: "price_tick" }> | null>(null);
  const url = useMemo(() => marketWebSocketUrl(marketCode), [marketCode]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      socket = new WebSocket(url);
      socket.onopen = () => setStatus("open");
      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(String(event.data)) as MarketStreamMessage;
          setLastMessage(message);
          if (message.type === "price_tick") {
            setPriceTick(message);
          }
        } catch {
          // Ignore malformed stream messages; the socket can keep carrying valid ticks.
        }
      };
      socket.onclose = () => {
        setStatus("closed");
        if (!stopped) {
          retryTimer = setTimeout(connect, 2500);
        }
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [url]);

  return { status, lastMessage, priceTick };
}

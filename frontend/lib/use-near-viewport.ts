"use client";
/**
 * Visibility-aware gating hook used by heavy evidence panels so they do
 * not compete with the first useful paint. Per the performance
 * preservation plan (Phase 3.1):
 *
 *   - It observes a container.
 *   - Once the container enters a generous root margin (default 800px)
 *     it returns true and stays true for that component instance —
 *     scrolling away does not wipe an already-loaded panel.
 *   - It gracefully returns true when IntersectionObserver is
 *     unavailable so older browsers and SSR snapshots still see all
 *     sections.
 */
import { useEffect, useRef, useState } from "react";

export type NearViewportOptions = {
  rootMargin?: string;
};

const DEFAULT_ROOT_MARGIN = "800px";

export function useNearViewport<T extends Element>(
  options: NearViewportOptions = {},
): { ref: React.MutableRefObject<T | null>; visible: boolean } {
  const ref = useRef<T | null>(null);
  const [visible, setVisible] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return typeof window.IntersectionObserver === "undefined";
  });

  useEffect(() => {
    if (visible) return;
    if (typeof window === "undefined") return;
    const node = ref.current;
    if (!node) return;
    if (typeof window.IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.disconnect();
            return;
          }
        }
      },
      { rootMargin: options.rootMargin ?? DEFAULT_ROOT_MARGIN },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible, options.rootMargin]);

  return { ref, visible };
}

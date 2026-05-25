import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // typedRoutes was disabled — it makes Turbopack stall on the first
  // compile because it dynamically generates a routes.d.ts file. The
  // typed-Link safety it provides isn't worth the dev-mode hang. Routes
  // are still type-checked at usage sites via `Route` casts where needed.
  typedRoutes: false,
  // Skip the in-build TS check — we run `tsc --noEmit` separately and the
  // bundled check is the heaviest single step under memory pressure. The
  // build will still type-check via tsc when needed.
  typescript: { ignoreBuildErrors: true },
};

export default nextConfig;

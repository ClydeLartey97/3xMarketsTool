import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  typedRoutes: true,
  // Skip the in-build TS check — we run `tsc --noEmit` separately and the
  // bundled check is the heaviest single step under memory pressure. The
  // build will still type-check via tsc when needed.
  typescript: { ignoreBuildErrors: true },
};

export default nextConfig;

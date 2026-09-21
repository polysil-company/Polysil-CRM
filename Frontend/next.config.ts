import type { NextConfig } from "next";

/**
 * Next.js configuration. Version-matched docs: node_modules/next/dist/docs/.
 * Any change here needs a changelog entry (type: chore or security).
 */

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

// TODO(OBS-002): add a Content-Security-Policy with a nonce once hosting is decided.
// The theme init script in the root layout is inline and will need that nonce.

const nextConfig: NextConfig = {
  reactCompiler: true,
  typedRoutes: true,
  poweredByHeader: false,
  headers() {
    return Promise.resolve([{ source: "/:path*", headers: securityHeaders }]);
  },
};

export default nextConfig;

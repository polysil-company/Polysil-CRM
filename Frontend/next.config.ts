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

/** Where the backend listens in local development (backend/infra/docker-compose.yml). */
const DEFAULT_API_PROXY_TARGET = "http://127.0.0.1:8000";

/**
 * The backend that /api/v1 is rewritten to (AUTH-001). The browser must reach the
 * API through this app's origin: the backend sends no CORS headers, and it scopes
 * its refresh cookie to /api/v1/auth on the host that set it.
 *
 * Read when the dev server starts and at build time, so each environment's build
 * needs its own value. Required for staging and production builds.
 */
function apiProxyTarget(): string {
  const raw = process.env.API_PROXY_TARGET?.trim() ?? "";
  const appEnv = process.env.NEXT_PUBLIC_APP_ENV;

  if (raw === "") {
    if (appEnv === "staging" || appEnv === "production") {
      throw new Error(`API_PROXY_TARGET is required when NEXT_PUBLIC_APP_ENV=${appEnv}.`);
    }
    return DEFAULT_API_PROXY_TARGET;
  }
  if (!URL.canParse(raw)) {
    throw new Error(
      `API_PROXY_TARGET must be an absolute URL such as http://127.0.0.1:8000, not "${raw}".`,
    );
  }
  return raw.replace(/\/+$/, "");
}

const nextConfig: NextConfig = {
  reactCompiler: true,
  typedRoutes: true,
  poweredByHeader: false,
  headers() {
    return Promise.resolve([{ source: "/:path*", headers: securityHeaders }]);
  },
  rewrites() {
    return Promise.resolve([
      { source: "/api/v1/:path*", destination: `${apiProxyTarget()}/api/v1/:path*` },
    ]);
  },
};

export default nextConfig;

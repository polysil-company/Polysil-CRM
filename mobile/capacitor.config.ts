import type { CapacitorConfig } from "@capacitor/cli";

/**
 * TRK-008 · The app is a shell around the live web app: it loads `server.url`, so screen and
 * logic changes reach phones without a new APK. The Next.js app can't be bundled as static files
 * (`src/proxy.ts`, dynamic routes).
 *
 * Capacitor documents `server.url` as meant for live reload, not production. We accept that on
 * purpose (the agreed approach) and keep it narrow: https only, no cleartext, navigation limited
 * to our own host, and a local page when the site can't be reached.
 *
 * Which site: `CAP_SERVER_URL` at build time (`npx cap sync android`). Without it, or empty, the
 * staging web app. A production APK must set it.
 */
const STAGING_URL = "https://polysil-test.pranayx.tech";

// Unset or empty (a CI input left blank) both mean staging.
const requested = process.env.CAP_SERVER_URL?.trim() ?? "";
const serverUrl = new URL(requested === "" ? STAGING_URL : requested);
if (serverUrl.protocol !== "https:") {
  throw new Error(`CAP_SERVER_URL must be https, not ${serverUrl.protocol}`);
}

const config: CapacitorConfig = {
  appId: "com.polysil.crm",
  appName: "Polysil",
  webDir: "www",
  server: {
    url: serverUrl.origin,
    cleartext: false,
    allowNavigation: [serverUrl.host],
    androidScheme: "https",
    errorPath: "offline.html",
  },
  android: {
    allowMixedContent: false,
    webContentsDebuggingEnabled: process.env.CAP_DEBUG === "true",
  },
};

export default config;

import { NextResponse, type NextRequest } from "next/server";

import { LOG_LEVEL_COOKIE } from "@/lib/logger/levels";
import { resolveServerLogLevel } from "@/lib/logger/runtime-level";

const ONE_DAY_SECONDS = 60 * 60 * 24;

/**
 * Runs before every page request (Node.js runtime).
 *
 * Log level sync: copies the server's runtime LOG_LEVEL into a readable
 * cookie, so browsers follow a LOG_LEVEL change on their next navigation —
 * no rebuild, no redeploy of the bundle. See Docs/Logging.md.
 *
 * TODO(AUTH-001): session checks and redirects for signed-out users belong here.
 */
export function proxy(request: NextRequest): NextResponse {
  const response = NextResponse.next();
  const level = resolveServerLogLevel();

  if (request.cookies.get(LOG_LEVEL_COOKIE)?.value !== level) {
    response.cookies.set({
      name: LOG_LEVEL_COOKIE,
      value: level,
      path: "/",
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      httpOnly: false, // the browser logger must read it
      maxAge: ONE_DAY_SECONDS,
    });
  }

  return response;
}

export const config = {
  matcher: [
    // Pages only: skip Next internals, API routes, the mock service worker and any file with an extension.
    "/((?!api|_next/static|_next/image|mockServiceWorker\\.js|.*\\..*).*)",
  ],
};

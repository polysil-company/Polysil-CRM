import { NextResponse, type NextRequest } from "next/server";

import { decideAuthRedirect } from "@/lib/auth/redirects";
import { SESSION_HINT_COOKIE } from "@/lib/auth/session-hint";
import { LOG_LEVEL_COOKIE } from "@/lib/logger/levels";
import { resolveServerLogLevel } from "@/lib/logger/runtime-level";

const ONE_DAY_SECONDS = 60 * 60 * 24;

/**
 * Runs before every page request (Node.js runtime).
 *
 * Signed-in routing (AUTH-006): sends visitors without a session to /sign-in,
 * remembering where they were going, and sends signed-in visitors away from it.
 * It reads a marker cookie, so the redirect is instant and nothing protected
 * flashes on screen. This is not security: the backend rejects every request
 * without a valid access token, whatever happens here.
 *
 * Log level sync: copies the server's runtime LOG_LEVEL into a readable
 * cookie, so browsers follow a LOG_LEVEL change on their next navigation —
 * no rebuild, no redeploy of the bundle. See Docs/Logging.md.
 */
export function proxy(request: NextRequest): NextResponse {
  const redirectTo = decideAuthRedirect({
    pathname: request.nextUrl.pathname,
    search: request.nextUrl.search,
    hasSession: request.cookies.get(SESSION_HINT_COOKIE)?.value === "1",
  });

  const response =
    redirectTo === null
      ? NextResponse.next()
      : NextResponse.redirect(new URL(redirectTo, request.url));
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

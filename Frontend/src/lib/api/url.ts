import { clientEnv } from "@/lib/env/client";

export type QueryPrimitive = string | number | boolean;

/** `undefined`, `null` and `""` are skipped; arrays become repeated keys (`status=a&status=b`). */
export type QueryValue = QueryPrimitive | null | undefined | readonly QueryPrimitive[];

export type QueryParams = Readonly<Record<string, QueryValue>>;

export type ApiPath = `/${string}`;

function isApiPath(path: string): path is ApiPath {
  return path.startsWith("/") && !path.startsWith("//");
}

/** A path an API response hands back (`/public/q/…/pdf`), or null when it is not one. */
export function asApiPath(path: string): ApiPath | null {
  return isApiPath(path) ? path : null;
}

/**
 * Builds a request URL from the configured API base and a path.
 *
 * Works with an absolute base (`https://api.example.com/v1`) and with the
 * same-origin base the app uses (`/api/v1`, rewritten to the backend by
 * next.config.ts). In a browser a same-origin URL is made absolute against the
 * page, so request mocks and every fetch implementation read it the same way.
 */
export function buildApiUrl(
  path: ApiPath,
  query?: QueryParams,
  baseUrl: string = clientEnv.apiBaseUrl,
): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query ?? {})) {
    const values: readonly QueryValue[] = Array.isArray(value) ? value : [value];
    for (const item of values) {
      if (item === undefined || item === null || item === "") {
        continue;
      }
      params.append(key, String(item));
    }
  }

  const search = params.toString();
  const url = `${baseUrl}${path}${search ? `?${search}` : ""}`;

  if (url.startsWith("/") && typeof window !== "undefined") {
    return new URL(url, window.location.origin).toString();
  }
  return url;
}

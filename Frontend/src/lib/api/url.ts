import { clientEnv } from "@/lib/env/client";

export type QueryPrimitive = string | number | boolean;

/** `undefined`, `null` and `""` are skipped; arrays become repeated keys (`status=a&status=b`). */
export type QueryValue = QueryPrimitive | null | undefined | readonly QueryPrimitive[];

export type QueryParams = Readonly<Record<string, QueryValue>>;

export type ApiPath = `/${string}`;

/**
 * Builds a request URL from the configured API base and a path.
 * Works with an absolute base (`https://api.example.com/v1`) and with a
 * same-origin base (`/api/v1`, for a Next.js rewrite in front of the backend).
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
  return `${baseUrl}${path}${search ? `?${search}` : ""}`;
}

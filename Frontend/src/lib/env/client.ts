import { z } from "zod";

/**
 * Public (browser-visible) environment variables, validated once at startup.
 *
 * `NEXT_PUBLIC_*` values are inlined into the bundle at BUILD time, so each
 * environment (feature preview, staging, production) needs its own build.
 * Each variable must be referenced statically below — `process.env[name]`
 * lookups are not inlined by Next.js.
 *
 * Invalid configuration throws during `next build`, so a misconfigured
 * staging or production build never ships. See Docs/Environments.md.
 */

export const APP_ENVS = ["development", "feature", "staging", "production"] as const;
export type AppEnv = (typeof APP_ENVS)[number];

export const API_MOCKING_MODES = ["enabled", "disabled"] as const;

const DEV_API_BASE_URL = "http://localhost:4000/api/v1";

/** Treats an empty string (`FOO=` in a .env file) as "not set". */
function emptyToUndefined(value: unknown): unknown {
  return value === "" ? undefined : value;
}

/** Accepts an absolute URL (`https://api.example.com/v1`) or a same-origin path (`/api/v1`). */
const apiBaseUrlSchema = z
  .string()
  .refine((value) => value.startsWith("/") || URL.canParse(value), {
    message: "must be an absolute URL or a path starting with /",
  })
  .transform((value) => value.replace(/\/+$/, ""));

export const clientEnvSchema = z
  .object({
    NEXT_PUBLIC_APP_ENV: z.preprocess(emptyToUndefined, z.enum(APP_ENVS).default("development")),
    NEXT_PUBLIC_API_BASE_URL: z.preprocess(emptyToUndefined, apiBaseUrlSchema.optional()),
    NEXT_PUBLIC_API_MOCKING: z.preprocess(emptyToUndefined, z.enum(API_MOCKING_MODES).optional()),
    NEXT_PUBLIC_RELEASE: z.preprocess(emptyToUndefined, z.string().default("local")),
  })
  .superRefine((env, ctx) => {
    const isDeployed =
      env.NEXT_PUBLIC_APP_ENV === "staging" || env.NEXT_PUBLIC_APP_ENV === "production";

    if (isDeployed && env.NEXT_PUBLIC_API_MOCKING === "enabled") {
      ctx.addIssue({
        code: "custom",
        path: ["NEXT_PUBLIC_API_MOCKING"],
        message: `mocking must be disabled in ${env.NEXT_PUBLIC_APP_ENV}`,
      });
    }

    if (isDeployed && env.NEXT_PUBLIC_API_BASE_URL === undefined) {
      ctx.addIssue({
        code: "custom",
        path: ["NEXT_PUBLIC_API_BASE_URL"],
        message: `required in ${env.NEXT_PUBLIC_APP_ENV}`,
      });
    }
  })
  .transform((env) => ({
    appEnv: env.NEXT_PUBLIC_APP_ENV,
    apiBaseUrl: env.NEXT_PUBLIC_API_BASE_URL ?? DEV_API_BASE_URL,
    // Mocks default ON only for local development and feature previews.
    apiMocking:
      env.NEXT_PUBLIC_API_MOCKING ??
      (env.NEXT_PUBLIC_APP_ENV === "development" || env.NEXT_PUBLIC_APP_ENV === "feature"
        ? "enabled"
        : "disabled"),
    release: env.NEXT_PUBLIC_RELEASE,
  }));

export type ClientEnv = z.output<typeof clientEnvSchema>;

/** Parses raw values; exported for tests. */
export function parseClientEnv(raw: Record<string, string | undefined>): ClientEnv {
  const result = clientEnvSchema.safeParse(raw);
  if (!result.success) {
    throw new Error(`Invalid public environment variables:\n${z.prettifyError(result.error)}`);
  }
  return result.data;
}

export const clientEnv: ClientEnv = parseClientEnv({
  NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_API_MOCKING: process.env.NEXT_PUBLIC_API_MOCKING,
  NEXT_PUBLIC_RELEASE: process.env.NEXT_PUBLIC_RELEASE,
});

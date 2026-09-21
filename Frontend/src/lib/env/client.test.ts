import { describe, expect, it } from "vitest";

import { parseClientEnv } from "./client";

describe("[OBS-002] public environment", () => {
  it("defaults to local development with mocks on", () => {
    expect(parseClientEnv({})).toEqual({
      appEnv: "development",
      apiBaseUrl: "/api/v1",
      apiMocking: "enabled",
      release: "local",
    });
  });

  it("treats empty values as unset", () => {
    expect(
      parseClientEnv({ NEXT_PUBLIC_APP_ENV: "", NEXT_PUBLIC_API_MOCKING: "" }).apiMocking,
    ).toBe("enabled");
  });

  it("turns mocks off by default in deployed environments", () => {
    const env = parseClientEnv({
      NEXT_PUBLIC_APP_ENV: "staging",
      NEXT_PUBLIC_API_BASE_URL: "https://staging.example.com/v1/",
    });
    expect(env.apiMocking).toBe("disabled");
    expect(env.apiBaseUrl).toBe("https://staging.example.com/v1");
  });

  it("refuses mocks in staging and production", () => {
    expect(() =>
      parseClientEnv({
        NEXT_PUBLIC_APP_ENV: "production",
        NEXT_PUBLIC_API_BASE_URL: "https://api.example.com",
        NEXT_PUBLIC_API_MOCKING: "enabled",
      }),
    ).toThrow(/mocking must be disabled in production/);
  });

  it("requires an API base URL in staging and production", () => {
    expect(() => parseClientEnv({ NEXT_PUBLIC_APP_ENV: "staging" })).toThrow(/required in staging/);
  });

  it("accepts a same-origin path and rejects anything that is not a URL", () => {
    expect(parseClientEnv({ NEXT_PUBLIC_API_BASE_URL: "/api/v1" }).apiBaseUrl).toBe("/api/v1");
    expect(() => parseClientEnv({ NEXT_PUBLIC_API_BASE_URL: "api.example.com" })).toThrow(
      /absolute URL/,
    );
  });

  it("rejects unknown environment names", () => {
    expect(() => parseClientEnv({ NEXT_PUBLIC_APP_ENV: "qa" })).toThrow(
      /Invalid public environment variables/,
    );
  });
});

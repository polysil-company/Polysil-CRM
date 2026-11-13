import { describe, expect, it } from "vitest";

import { maskEmail, maskPhone, redact, REDACTED } from "./redact";

describe("[OBS-001] redact", () => {
  it("removes secrets by key name, including common suffixes", () => {
    expect(
      redact({
        password: "hunter2",
        otp: "123456",
        accessToken: "abc",
        webhookSecret: "shh",
        Authorization: "Bearer xyz",
        pan: "ABCDE1234F",
        ifsc_code: "SBIN0000001",
      }),
    ).toEqual({
      password: REDACTED,
      otp: REDACTED,
      accessToken: REDACTED,
      webhookSecret: REDACTED,
      Authorization: REDACTED,
      pan: REDACTED,
      ifsc_code: REDACTED,
    });
  });

  it("does not redact keys that merely contain a secret word", () => {
    expect(redact({ company: "Polysil", pincode: "390001", expand: true })).toEqual({
      company: "Polysil",
      pincode: "390001",
      expand: true,
    });
  });

  it("masks phone numbers and emails instead of removing them", () => {
    expect(
      redact({
        phone: "+91 98123 45678",
        mobileNumber: "9812345678",
        ownerEmail: "ramesh.patel@example.com",
      }),
    ).toEqual({ phone: "******5678", mobileNumber: "******5678", ownerEmail: "r***@example.com" });
    expect(maskPhone("12")).toBe("****");
    expect(maskEmail("not-an-email")).toBe(REDACTED);
  });

  it("keeps null and undefined secrets as they are", () => {
    expect(redact({ password: null, token: undefined })).toEqual({
      password: null,
      token: undefined,
    });
  });

  it("marks circular references without breaking shared ones", () => {
    const shared = { x: 1 };
    const node: Record<string, unknown> = { name: "root", a: shared, b: shared };
    node.self = node;

    expect(redact(node)).toEqual({ name: "root", a: { x: 1 }, b: { x: 1 }, self: "[Circular]" });
  });

  it("bounds the size of strings, arrays and nesting", () => {
    const long = "a".repeat(600);
    const truncated = redact(long);
    expect(typeof truncated === "string" && truncated.startsWith("a".repeat(500))).toBe(true);
    expect(truncated).toContain("[+100 chars]");

    const array = redact(Array.from({ length: 30 }, (_, index) => index));
    expect(Array.isArray(array) ? array.at(-1) : undefined).toBe("[+5 more items]");

    const deep = { l1: { l2: { l3: { l4: { l5: { l6: { l7: "bottom" } } } } } } };
    expect(JSON.stringify(redact(deep))).toContain("[MaxDepth]");
  });

  it("serialises errors with their cause", () => {
    const result = redact(new Error("boom", { cause: new Error("root cause") }));
    expect(result).toMatchObject({
      name: "Error",
      message: "boom",
      cause: { message: "root cause" },
    });
  });

  it("handles dates, bigints and functions", () => {
    expect(redact(new Date("2026-09-14T10:00:00.000Z"))).toBe("2026-09-14T10:00:00.000Z");
    expect(redact(new Date("invalid"))).toBe("[Invalid Date]");
    expect(redact(10n)).toBe("10");
    expect(redact(() => undefined)).toBe("[Function]");
  });

  it("never throws, even when reading a value throws", () => {
    const hostile = {
      get value(): string {
        throw new Error("getter exploded");
      },
    };
    expect(redact(hostile)).toBe("[Unserializable]");
  });
});

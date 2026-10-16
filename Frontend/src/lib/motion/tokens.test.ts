import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { DURATION, EASE } from "./tokens";

const css = readFileSync(path.resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

function cssVariable(name: string): string {
  const match = new RegExp(`--${name}:\\s*([^;]+);`).exec(css);
  const value = match?.[1];
  if (value === undefined) {
    throw new Error(`--${name} is not defined in src/styles/tokens.css`);
  }
  return value.trim();
}

function bezier(value: string): number[] {
  const inner = /cubic-bezier\(([^)]+)\)/.exec(value)?.[1] ?? "";
  return inner.split(",").map((part) => Number(part.trim()));
}

describe("[DS-001] motion tokens mirror tokens.css", () => {
  it.each([
    { name: "ease-out", expected: EASE.out },
    { name: "ease-in-out", expected: EASE.inOut },
    { name: "ease-drawer", expected: EASE.drawer },
  ])("--$name", ({ name, expected }) => {
    expect(bezier(cssVariable(name))).toEqual(expected);
  });

  it.each([
    { name: "duration-instant", seconds: DURATION.instant },
    { name: "duration-press", seconds: DURATION.press },
    { name: "duration-fast", seconds: DURATION.fast },
    { name: "duration-base", seconds: DURATION.base },
    { name: "duration-slow", seconds: DURATION.slow },
  ])("--$name", ({ name, seconds }) => {
    expect(cssVariable(name)).toBe(`${Math.round(seconds * 1000)}ms`);
  });

  it("uses the strong ease-out for Tailwind's default transition curve", () => {
    expect(bezier(cssVariable("default-transition-timing-function"))).toEqual(EASE.out);
  });
});

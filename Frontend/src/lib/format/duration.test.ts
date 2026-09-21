import { describe, expect, it } from "vitest";

import { describeCountdown, formatCountdown } from "./duration";

describe("[AUTH-001] countdown formatting", () => {
  it.each([
    [272, "4:32"],
    [300, "5:00"],
    [9, "0:09"],
    [0, "0:00"],
    [-5, "0:00"],
    [12.9, "0:12"],
    [Number.NaN, "0:00"],
  ])("shows %s seconds as %s", (seconds, expected) => {
    expect(formatCountdown(seconds)).toBe(expected);
  });

  it.each([
    [272, "4 minutes 32 seconds"],
    [60, "1 minute"],
    [61, "1 minute 1 second"],
    [1, "1 second"],
    [0, "0 seconds"],
  ])("reads %s seconds as %s", (seconds, expected) => {
    expect(describeCountdown(seconds)).toBe(expected);
  });
});

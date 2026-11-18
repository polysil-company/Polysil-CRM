import { describe, expect, it } from "vitest";

import { autostartHelp, dutyBlockers, serverEndText, uploadProblem } from "./duty-labels";

const ALL_SET = {
  location: "granted",
  background: "granted",
  notifications: "granted",
  batteryUnrestricted: true,
  gpsOn: true,
} as const;

describe("[TRK-008] Duty's words", () => {
  it("lists what still stops duty, in the order to do it", () => {
    expect(dutyBlockers(ALL_SET)).toEqual([]);
    expect(dutyBlockers({ ...ALL_SET, location: "prompt", batteryUnrestricted: false })).toEqual([
      "location",
      "battery",
    ]);
    // "Allow all the time" is asked once location itself is allowed.
    expect(dutyBlockers({ ...ALL_SET, background: "denied", gpsOn: false })).toEqual([
      "background",
      "gps",
    ]);
    expect(dutyBlockers({ ...ALL_SET, notifications: "denied" })).toEqual(["notifications"]);
  });

  it("says an upload problem calmly when points are only waiting", () => {
    expect(uploadProblem(null)).toBeNull();
    expect(uploadProblem("offline")?.tone).toBe("calm");
    expect(uploadProblem("waiting_for_sign_in")?.tone).toBe("calm");
    expect(uploadProblem("bad_clock")).toMatchObject({ tone: "warn" });
    expect(uploadProblem("refused:validation_error")?.tone).toBe("warn");
  });

  it("names why the server ended a duty", () => {
    expect(serverEndText("auto")).toBe("Duty ended after working hours.");
    expect(serverEndText(null)).toBe("Duty was ended by the server.");
  });

  it("links autostart advice for the phone's maker only", () => {
    expect(autostartHelp("Xiaomi")).toEqual({
      brand: "Xiaomi",
      url: "https://dontkillmyapp.com/xiaomi",
    });
    expect(autostartHelp("POCO")?.url).toBe("https://dontkillmyapp.com/xiaomi");
    expect(autostartHelp("vivo")?.brand).toBe("Vivo");
    expect(autostartHelp("Google")).toBeNull();
  });
});

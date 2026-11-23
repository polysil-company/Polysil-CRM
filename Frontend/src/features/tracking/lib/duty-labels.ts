import type { DutyEndReason } from "@/features/tracking/api/duty.schemas";
import type { TrackingPermissions } from "@/features/tracking/native/tracking-bridge";

/**
 * TRK-008 · The Duty screen's words: what still stops duty from starting, what an upload problem
 * means, why the server ended a duty, and where a phone's maker hides its autostart switch.
 */

export type DutyBlocker = "location" | "background" | "battery" | "notifications" | "gps";

/** What must be done before duty can start, in the order to do it. */
export function dutyBlockers(permissions: TrackingPermissions): DutyBlocker[] {
  const blockers: DutyBlocker[] = [];
  if (permissions.location !== "granted") blockers.push("location");
  else if (permissions.background !== "granted") blockers.push("background");
  if (!permissions.batteryUnrestricted) blockers.push("battery");
  if (permissions.notifications !== "granted") blockers.push("notifications");
  if (!permissions.gpsOn) blockers.push("gps");
  return blockers;
}

export const BLOCKER_COPY: Readonly<
  Record<DutyBlocker, { readonly title: string; readonly body: string; readonly action: string }>
> = {
  location: {
    title: "Allow location",
    body: "Your route is recorded only while you're on duty.",
    action: "Allow location",
  },
  background: {
    title: 'Set location to "Allow all the time"',
    body: "So your route keeps recording with the screen off or the app in the background.",
    action: "Open the setting",
  },
  battery: {
    title: "Turn battery optimisation off for Polysil",
    body: "Otherwise the phone stops the app to save battery, and your route has gaps.",
    action: "Open the setting",
  },
  notifications: {
    title: "Allow notifications",
    body: 'Android shows "Tracking on duty" while your route is recorded.',
    action: "Allow notifications",
  },
  gps: {
    title: "Turn on location (GPS)",
    body: "The phone's location switch is off.",
    action: "Turn it on",
  },
};

/** What an upload problem means for the person, or null when there is none worth saying. */
export function uploadProblem(lastError: string | null): {
  readonly tone: "calm" | "warn";
  readonly text: string;
} | null {
  if (lastError === null) return null;
  if (lastError === "offline") {
    return {
      tone: "calm",
      text: "No connection. Points are kept on the phone and go up when it's back.",
    };
  }
  if (lastError === "waiting_for_sign_in") {
    return {
      tone: "calm",
      text: "Points are kept on the phone and go up the next time the app is open.",
    };
  }
  if (lastError === "bad_clock") {
    return {
      tone: "warn",
      text: "The phone's clock is wrong. Set date and time to automatic in the phone's settings.",
    };
  }
  if (lastError === "forbidden") {
    return { tone: "warn", text: "Your role doesn't record a route, so duty has stopped." };
  }
  if (lastError === "location_denied") {
    return { tone: "warn", text: "Location was turned off for Polysil, so no route is recorded." };
  }
  return {
    tone: "warn",
    text: "Some points couldn't be sent. Ask your administrator if it keeps happening.",
  };
}

export const SERVER_END_COPY: Readonly<Record<DutyEndReason, string>> = {
  user: "Duty ended.",
  auto: "Duty ended after working hours.",
  consent_withdrawn: "Duty ended: tracking consent was withdrawn.",
  deactivated: "Duty ended: your account was switched off.",
};

export function serverEndText(reason: string | null): string {
  const known = Object.entries(SERVER_END_COPY).find(([key]) => key === reason);
  return known?.[1] ?? "Duty was ended by the server.";
}

/** dontkillmyapp.com's page for the phone's maker, for its autostart setting; null for others. */
export function autostartHelp(
  manufacturer: string,
): { readonly brand: string; readonly url: string } | null {
  const maker = manufacturer.trim().toLowerCase();
  const pages: readonly (readonly [readonly string[], string, string])[] = [
    [["xiaomi", "redmi", "poco"], "Xiaomi", "xiaomi"],
    [["oppo"], "Oppo", "oppo"],
    [["realme"], "Realme", "realme"],
    [["vivo"], "Vivo", "vivo"],
    [["oneplus"], "OnePlus", "oneplus"],
    [["samsung"], "Samsung", "samsung"],
  ];
  const page = pages.find(([makers]) => makers.includes(maker));
  return page === undefined
    ? null
    : { brand: page[1], url: `https://dontkillmyapp.com/${page[2]}` };
}

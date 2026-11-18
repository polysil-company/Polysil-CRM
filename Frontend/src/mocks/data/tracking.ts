import type {
  RouteWire,
  TeamMemberWire,
  VisitWire,
} from "@/features/tracking/api/tracking.schemas";

import { mockUuid } from "./reference";

/** The mock's own id space for duties, visits and stops. */
export const TRACKING_SPACE = 0x7a0c;

const MINUTE = 60_000;

interface MockTracked {
  readonly id: string;
  readonly name: string;
  readonly role: string;
  /** Where their day starts: a town they work from. */
  readonly home: readonly [number, number];
  readonly state: "on_duty" | "stale" | "off_duty";
  readonly batteryPct: number | null;
  readonly isMock: boolean;
  readonly openVisitLabel: string | null;
}

/**
 * The people a manager may track in the mock: field officers around Saurashtra and one
 * District Manager. One is silent (stale), one is off duty, one's phone reports a fake
 * location. The signed-in mock staff member (`usr-001`) is the first, so a field officer
 * sees themselves.
 */
export const MOCK_TRACKED: readonly MockTracked[] = [
  {
    id: "usr-001",
    name: "Aarav Desai",
    role: "field_officer",
    home: [22.3039, 70.8022],
    state: "on_duty",
    batteryPct: 64,
    isMock: false,
    openVisitLabel: "POL/GJ/2026-27/00079",
  },
  {
    id: "usr-201",
    name: "Ravi Patel",
    role: "field_officer",
    home: [21.5222, 70.4579],
    state: "on_duty",
    batteryPct: 81,
    isMock: false,
    openVisitLabel: null,
  },
  {
    id: "usr-202",
    name: "Kiran Solanki",
    role: "field_officer",
    home: [21.6032, 71.2221],
    state: "stale",
    batteryPct: 12,
    isMock: false,
    openVisitLabel: null,
  },
  {
    id: "usr-203",
    name: "Meena Chauhan",
    role: "field_officer",
    home: [21.7645, 72.1519],
    state: "on_duty",
    batteryPct: 47,
    isMock: true,
    openVisitLabel: null,
  },
  {
    id: "usr-204",
    name: "Jignesh Rathod",
    role: "field_officer",
    home: [22.8173, 70.8378],
    state: "off_duty",
    batteryPct: null,
    isMock: false,
    openVisitLabel: null,
  },
  {
    id: "usr-205",
    name: "Hetal Shah",
    role: "district_manager",
    home: [23.0225, 72.5714],
    state: "on_duty",
    batteryPct: 93,
    isMock: false,
    openVisitLabel: null,
  },
];

/** A small, stable number from text, so every mock route is the same on every load. */
function seedOf(text: string): number {
  let hash = 2166136261;
  for (const char of text) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash);
}

/** A repeatable sequence of numbers between 0 and 1. */
function sequence(seed: number): () => number {
  let state = seed % 2147483647 || 1;
  return () => {
    state = (state * 48271) % 2147483647;
    return state / 2147483647;
  };
}

/** Kilometres between two points on the earth, by the haversine formula. */
export function kmBetween(from: readonly [number, number], to: readonly [number, number]): number {
  const rad = Math.PI / 180;
  const dLat = (to[0] - from[0]) * rad;
  const dLng = (to[1] - from[1]) * rad;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(from[0] * rad) * Math.cos(to[0] * rad) * Math.sin(dLng / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** "2026-10-18" at "09:15" in India, as an instant. */
function atIst(date: string, hour: number, minute: number): number {
  return Date.parse(
    `${date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+05:30`,
  );
}

function iso(ms: number): string {
  return new Date(ms).toISOString();
}

/** TRK-001 · The team map's rows, as `team_latest()` returns them. */
export function mockTeamLatest(now: number = Date.now()): TeamMemberWire[] {
  return MOCK_TRACKED.map((person, index) => {
    const onDuty = person.state !== "off_duty";
    const silentFor = person.state === "stale" ? 42 : 2 + index;
    const jitter = sequence(seedOf(person.id));
    const lat = person.home[0] + (jitter() - 0.5) * 0.08;
    const lng = person.home[1] + (jitter() - 0.5) * 0.08;
    return {
      user: { id: person.id, full_name: person.name },
      role: person.role,
      on_duty: onDuty,
      last_seen_at: onDuty ? iso(now - silentFor * MINUTE) : iso(now - 16 * 60 * MINUTE),
      lat: onDuty ? lat : null,
      lng: onDuty ? lng : null,
      accuracy_m: onDuty ? 8 + index * 3 : null,
      battery_pct: person.batteryPct,
      is_mock: person.isMock,
      stale: person.state === "stale",
      open_visit:
        person.openVisitLabel === null
          ? null
          : {
              id: mockUuid(TRACKING_SPACE, 900 + index),
              label: person.openVisitLabel,
              since: iso(now - 26 * MINUTE),
            },
    };
  });
}

/**
 * TRK-002 · One person's day: a drive out through three villages with a stop at each, two of
 * them visits, and back. Empty for a day ahead, and for someone off duty today.
 */
export function mockRoute(
  person: MockTracked,
  date: string,
  leadLabels: readonly { id: string; label: string }[],
  now: number = Date.now(),
): RouteWire {
  const empty: RouteWire = {
    user: { id: person.id, full_name: person.name },
    date,
    duty: [],
    points: [],
    stops: [],
    visits: [],
    distance_km: "0.0",
    point_count: 0,
    dropped_points: 0,
    mock_points: 0,
  };
  const start = atIst(date, 9, 10);
  if (start > now) return empty;
  const today = atIst(date, 0, 0) <= now && now < atIst(date, 24, 0);
  if (today && person.state === "off_duty") return empty;

  const random = sequence(seedOf(`${person.id}:${date}`));
  const waypoints: [number, number][] = [[person.home[0], person.home[1]]];
  for (let index = 0; index < 3; index += 1) {
    const previous = waypoints[waypoints.length - 1] ?? [person.home[0], person.home[1]];
    waypoints.push([previous[0] + (random() - 0.4) * 0.09, previous[1] + (random() - 0.4) * 0.11]);
  }
  waypoints.push([person.home[0], person.home[1]]);

  const points: RouteWire["points"] = [];
  const stops: RouteWire["stops"] = [];
  const visits: VisitWire[] = [];
  let clock = start;
  let distance = 0;
  const end = today ? Math.min(now, atIst(date, 18, 40)) : atIst(date, 18, 40);

  for (let leg = 0; leg < waypoints.length - 1 && clock < end; leg += 1) {
    const from = waypoints[leg] ?? waypoints[0];
    const to = waypoints[leg + 1] ?? waypoints[0];
    if (from === undefined || to === undefined) break;
    const steps = 24;
    for (let step = 0; step <= steps && clock < end; step += 1) {
      const t = step / steps;
      const lat = from[0] + (to[0] - from[0]) * t + (random() - 0.5) * 0.002;
      const lng = from[1] + (to[1] - from[1]) * t + (random() - 0.5) * 0.002;
      const last = points[points.length - 1];
      if (last !== undefined) distance += kmBetween([last.lat, last.lng], [lat, lng]);
      points.push({
        at: iso(clock),
        lat,
        lng,
        accuracy_m: 6 + Math.round(random() * 14),
        is_mock: person.isMock && step % 6 === 0,
      });
      clock += 2 * MINUTE;
    }
    if (leg < waypoints.length - 2 && clock < end) {
      const minutes = 15 + Math.round(random() * 30);
      const lead =
        leg < 2
          ? leadLabels[(seedOf(person.id) + leg) % Math.max(1, leadLabels.length)]
          : undefined;
      const visitId =
        lead === undefined
          ? null
          : mockUuid(TRACKING_SPACE, (seedOf(`${person.id}${date}`) % 1000) * 10 + leg);
      stops.push({
        from: iso(clock),
        to: iso(clock + minutes * MINUTE),
        minutes,
        lat: to[0],
        lng: to[1],
        visit_id: visitId,
      });
      if (lead !== undefined && visitId !== null) {
        visits.push({
          id: visitId,
          user: { id: person.id, full_name: person.name },
          lead: { id: lead.id, label: lead.label },
          partner: null,
          task_id: null,
          place_name: null,
          checkin_at: iso(clock + 2 * MINUTE),
          checkin: { lat: to[0], lng: to[1], accuracy_m: 9 },
          checkout_at: iso(clock + (minutes - 2) * MINUTE),
          checkout: { lat: to[0], lng: to[1], accuracy_m: 11 },
          duration_minutes: minutes - 4,
          outcome: leg === 0 ? "met" : "follow_up",
          note: leg === 0 ? "Wants a quote for 2 acres of drip." : "Call back after the harvest.",
          auto_closed: false,
          photo_count: leg === 0 ? 1 : 0,
        });
      }
      clock += minutes * MINUTE;
    }
  }

  const ended = today && person.state !== "off_duty" ? null : iso(Math.min(clock, end));
  const mockPoints = points.filter((point) => point.is_mock).length;
  return {
    ...empty,
    duty: [
      {
        id: mockUuid(TRACKING_SPACE, seedOf(`${person.id}${date}`) % 100_000),
        started_at: iso(start),
        ended_at: ended,
        end_reason: ended === null ? null : "user",
      },
    ],
    points,
    stops,
    visits,
    distance_km: distance.toFixed(1),
    point_count: points.length + 7,
    dropped_points: 7,
    mock_points: mockPoints,
  };
}

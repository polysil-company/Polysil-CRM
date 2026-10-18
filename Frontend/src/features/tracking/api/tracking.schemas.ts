import { z } from "zod";

/**
 * TRK-001, TRK-002 · Field tracking (`field-tracking-contract.md`, generated `tracking.md`,
 * migration 030): the team map and one person's day. Coordinates are degrees; times carry an
 * offset; a day is an Indian calendar day.
 */

const id = z.string().min(1);
const isoDateTime = z.iso.datetime({ offset: true });
const latitude = z.number().min(-90).max(90);
const longitude = z.number().min(-180).max(180);
const userRef = z.object({ id, full_name: z.string() });

const teamMemberWireSchema = z.object({
  user: userRef,
  role: z.string().nullable(),
  on_duty: z.boolean(),
  last_seen_at: isoDateTime.nullable(),
  /** Null when off duty. */
  lat: latitude.nullable(),
  lng: longitude.nullable(),
  accuracy_m: z.number().nullable(),
  battery_pct: z.number().int().min(0).max(100).nullable(),
  /** The phone reported a fake location. */
  is_mock: z.boolean(),
  /** On duty, but silent for 15 minutes. */
  stale: z.boolean(),
  open_visit: z.object({ id, label: z.string(), since: isoDateTime }).nullable(),
});
export type TeamMemberWire = z.input<typeof teamMemberWireSchema>;

/** Where a person is on the team map: on duty and heard from, on duty but silent, or off. */
export type TeamMemberState = "on_duty" | "stale" | "off_duty";

function stateOf(row: { readonly on_duty: boolean; readonly stale: boolean }): TeamMemberState {
  if (!row.on_duty) return "off_duty";
  return row.stale ? "stale" : "on_duty";
}

export const teamLatestSchema = z
  .object({ data: z.array(teamMemberWireSchema) })
  .transform(({ data }) =>
    data.map((row) => ({
      id: row.user.id,
      name: row.user.full_name,
      role: row.role,
      state: stateOf(row),
      lastSeenAt: row.last_seen_at,
      position:
        row.lat === null || row.lng === null
          ? null
          : { lat: row.lat, lng: row.lng, accuracyM: row.accuracy_m },
      batteryPct: row.battery_pct,
      isMock: row.is_mock,
      openVisit: row.open_visit,
    })),
  );
export type TeamMember = z.output<typeof teamLatestSchema>[number];

const positionSchema = z.object({
  lat: latitude,
  lng: longitude,
  accuracy_m: z.number().nullish(),
});

export const VISIT_OUTCOMES = ["met", "not_available", "follow_up", "other"] as const;
export type VisitOutcome = (typeof VISIT_OUTCOMES)[number];

const docRef = z.object({ id, label: z.string() });

export const visitWireSchema = z.object({
  id,
  user: userRef,
  lead: docRef.nullable(),
  partner: docRef.nullable(),
  task_id: z.string().nullable(),
  place_name: z.string().nullable(),
  checkin_at: isoDateTime,
  checkin: positionSchema,
  checkout_at: isoDateTime.nullable(),
  checkout: positionSchema.nullable(),
  duration_minutes: z.number().int().nonnegative().nullable(),
  outcome: z.enum(VISIT_OUTCOMES).nullable(),
  note: z.string().nullable(),
  /** Closed by the server 12 hours after check-in. */
  auto_closed: z.boolean(),
  photo_count: z.number().int().nonnegative(),
});
export type VisitWire = z.input<typeof visitWireSchema>;

/** A visit as the screens read it. */
export interface Visit {
  readonly id: string;
  readonly user: { readonly id: string; readonly name: string };
  readonly lead: { readonly id: string; readonly label: string } | null;
  readonly partner: { readonly id: string; readonly label: string } | null;
  readonly taskId: string | null;
  readonly placeName: string | null;
  /** What the visit was to: the lead's number, the dealer, or the place typed. */
  readonly label: string;
  readonly checkinAt: string;
  readonly checkin: {
    readonly lat: number;
    readonly lng: number;
    readonly accuracyM: number | null;
  };
  readonly checkoutAt: string | null;
  readonly durationMinutes: number | null;
  readonly outcome: VisitOutcome | null;
  readonly note: string | null;
  readonly autoClosed: boolean;
  readonly photoCount: number;
}

export function visitOf(wire: z.output<typeof visitWireSchema>): Visit {
  return {
    id: wire.id,
    user: { id: wire.user.id, name: wire.user.full_name },
    lead: wire.lead,
    partner: wire.partner,
    taskId: wire.task_id,
    placeName: wire.place_name,
    label: wire.lead?.label ?? wire.partner?.label ?? wire.place_name ?? "A visit",
    checkinAt: wire.checkin_at,
    checkin: {
      lat: wire.checkin.lat,
      lng: wire.checkin.lng,
      accuracyM: wire.checkin.accuracy_m ?? null,
    },
    checkoutAt: wire.checkout_at,
    durationMinutes: wire.duration_minutes,
    outcome: wire.outcome,
    note: wire.note,
    autoClosed: wire.auto_closed,
    photoCount: wire.photo_count,
  };
}

export const DUTY_END_REASONS = ["user", "auto", "consent_withdrawn", "deactivated"] as const;

const routeWireSchema = z.object({
  user: userRef,
  date: z.iso.date(),
  duty: z.array(
    z.object({
      id,
      started_at: isoDateTime,
      ended_at: isoDateTime.nullable(),
      end_reason: z.string().nullable(),
    }),
  ),
  /** Oldest first, at most 2,000 for drawing. */
  points: z.array(
    z.object({
      at: isoDateTime,
      lat: latitude,
      lng: longitude,
      accuracy_m: z.number().nullable(),
      is_mock: z.boolean(),
    }),
  ),
  /** 10 minutes or more within 150 m. */
  stops: z.array(
    z.object({
      from: isoDateTime,
      to: isoDateTime,
      minutes: z.number().int().nonnegative(),
      lat: latitude,
      lng: longitude,
      visit_id: z.string().nullable(),
    }),
  ),
  visits: z.array(visitWireSchema),
  /** One decimal, as a string. */
  distance_km: z.string().regex(/^\d+(\.\d+)?$/),
  point_count: z.number().int().nonnegative(),
  dropped_points: z.number().int().nonnegative(),
  mock_points: z.number().int().nonnegative(),
});
export type RouteWire = z.input<typeof routeWireSchema>;

export const routeSchema = z.object({ data: routeWireSchema }).transform(({ data }) => ({
  user: { id: data.user.id, name: data.user.full_name },
  date: data.date,
  duty: data.duty.map((span) => ({
    id: span.id,
    startedAt: span.started_at,
    endedAt: span.ended_at,
    endReason: span.end_reason,
  })),
  points: data.points.map((point) => ({
    at: point.at,
    lat: point.lat,
    lng: point.lng,
    isMock: point.is_mock,
  })),
  stops: data.stops.map((stop) => ({
    from: stop.from,
    to: stop.to,
    minutes: stop.minutes,
    lat: stop.lat,
    lng: stop.lng,
    visitId: stop.visit_id,
  })),
  visits: data.visits.map(visitOf),
  distanceKm: Number(data.distance_km),
  pointCount: data.point_count,
  droppedPoints: data.dropped_points,
  mockPoints: data.mock_points,
}));
export type Route = z.output<typeof routeSchema>;

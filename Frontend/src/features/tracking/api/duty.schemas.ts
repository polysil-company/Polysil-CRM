import { z } from "zod";

/**
 * TRK-008 · Going on and off duty from the Android app (`field-tracking-contract.md` §1, §3).
 * The phone makes the id; the answer's id is the one to use, since a reinstall mid-duty gets the
 * open session back.
 */

const isoDateTime = z.iso.datetime({ offset: true });

export const DUTY_END_REASONS = ["user", "auto", "consent_withdrawn", "deactivated"] as const;
export type DutyEndReason = (typeof DUTY_END_REASONS)[number];

const dutyWireSchema = z.object({
  id: z.string().min(1),
  started_at: isoDateTime,
  ended_at: isoDateTime.nullable(),
  end_reason: z.enum(DUTY_END_REASONS).nullable(),
  /** Started outside the working hours the admin set. */
  outside_hours: z.boolean().default(false),
});
export type DutyWire = z.input<typeof dutyWireSchema>;

export const dutySchema = z.object({ data: dutyWireSchema }).transform(({ data }) => ({
  id: data.id,
  startedAt: data.started_at,
  endedAt: data.ended_at,
  endReason: data.end_reason,
  outsideHours: data.outside_hours,
}));
export type Duty = z.output<typeof dutySchema>;

/** `POST /tracking/duty/start`: one fresh fix, and the phone's clock when sending. */
export interface DutyStartRequest {
  readonly id: string;
  readonly device_id: string;
  readonly at: string;
  readonly sent_at: string;
  readonly lat: number;
  readonly lng: number;
  readonly accuracy_m: number | null;
}

/** `POST /tracking/duty/end`. Ending an ended duty answers it unchanged. */
export interface DutyEndRequest {
  readonly id: string;
  readonly at: string;
  readonly sent_at: string;
  readonly lat: number;
  readonly lng: number;
  readonly accuracy_m: number | null;
}

/**
 * TRK-009 · `POST /tracking/device-token` (BE-032, contract §1 step 3a): the phone's own token for
 * location batches, duty end and the tracking config. 30 days, and only while this sign-in lives.
 * `token` is shown once; the server keeps only its hash.
 */
const deviceTokenWireSchema = z.object({
  token: z.string().startsWith("pdt_").nullable(),
  user_id: z.string().min(1),
  device_id: z.string().min(1),
  expires_at: isoDateTime,
});
export type DeviceTokenWire = z.input<typeof deviceTokenWireSchema>;

export const deviceTokenSchema = z
  .object({ data: deviceTokenWireSchema })
  .transform(({ data }) => ({
    token: data.token,
    userId: data.user_id,
    deviceId: data.device_id,
    expiresAt: data.expires_at,
  }));
export type DeviceToken = z.output<typeof deviceTokenSchema>;

import { z } from "zod";

/** The URL parameter that carries a record to attach to the next message. */
export const SHARE_PARAM = "share";

/** A record to attach to a message. Only leads can be shared today. */
export interface ShareAttachment {
  readonly type: "lead";
  readonly id: string;
}

const LEAD_PREFIX = "lead:";

const shareParamSchema = z.string().regex(/^lead:[A-Za-z0-9_-]{1,64}$/);

/** `?share=lead:lead-10001` → the lead to attach. Anything else is ignored. */
export function parseShareParam(value: string | null): ShareAttachment | null {
  const parsed = shareParamSchema.safeParse(value);
  return parsed.success ? { type: "lead", id: parsed.data.slice(LEAD_PREFIX.length) } : null;
}

export function toShareParam(attachment: ShareAttachment): string {
  return `${attachment.type}:${attachment.id}`;
}

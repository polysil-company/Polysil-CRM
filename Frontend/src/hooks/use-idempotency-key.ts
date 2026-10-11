"use client";

import { useRef } from "react";

import { createRequestId } from "@/lib/api/request-id";

export interface IdempotencyKeys {
  /** The key for this request body: the same body gets the same key until `reset`. */
  keyFor: (body: unknown) => string;
  /** Forget the last body, so the next request gets a fresh key. Call after a success. */
  reset: () => void;
}

/**
 * One Idempotency-Key per distinct request body. A retry of the same save reuses the key,
 * so a save whose reply was lost is replayed by the backend instead of done twice; changing
 * any detail makes a new key (the same key with a different body is a 409).
 */
export function useIdempotencyKey(): IdempotencyKeys {
  const last = useRef<{ body: string; key: string } | null>(null);

  return {
    keyFor: (body) => {
      const serialized = JSON.stringify(body);
      if (last.current?.body !== serialized) {
        last.current = { body: serialized, key: createRequestId() };
      }
      return last.current.key;
    },
    reset: () => {
      last.current = null;
    },
  };
}

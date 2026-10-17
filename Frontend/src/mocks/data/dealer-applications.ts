import type { DealerApplicationWire } from "@/features/dealer-applications/api/dealer-applications.schemas";

/**
 * CHNL-007 · A dealer application as the mock backend keeps it: the wire fields that are
 * stored, with the link's token (the backend keeps only its hash) and who started it.
 */
export interface MockDealerApplication extends Omit<
  DealerApplicationWire,
  "missing" | "can" | "apply_url" | "created_by"
> {
  token: string;
  created_by: { id: string; full_name: string } | null;
  submitted_at: string | null;
}

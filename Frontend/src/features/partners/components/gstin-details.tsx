"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { gstinLookupQueryOptions } from "@/features/partners/api/partners.queries";
import type { GstinLookup } from "@/features/partners/api/partners.schemas";

/** What the GST record fills in: the business name, its PAN and its address. */
export interface GstinFill {
  readonly name: string;
  readonly pan: string | null;
  readonly address: string | null;
}

/** The name a partner trades under, else its legal name. Null when the record gives neither. */
export function gstinFillOf(lookup: GstinLookup): GstinFill | null {
  const name = lookup.tradeName ?? lookup.legalName;
  return name === null ? null : { name, pan: lookup.pan, address: lookup.address };
}

/**
 * CHNL-006 · Under a complete GSTIN: what the GST record says (FS-053). When it is found, one
 * click fills the business name, PAN and address, which stay editable. When the backend has
 * no GST data provider yet, or the record isn't found, the names are typed as before.
 */
export function GstinDetails({
  gstin,
  onUse,
}: {
  /** A complete, well-formed GSTIN, upper case. */
  gstin: string;
  onUse: (fill: GstinFill) => void;
}): React.JSX.Element | null {
  const lookup = useQuery(gstinLookupQueryOptions(gstin));

  if (lookup.status === "pending") {
    return (
      <p role="status" className="text-xs text-muted-foreground">
        Checking the GST record…
      </p>
    );
  }
  if (lookup.status === "error") {
    return (
      <p className="text-xs text-muted-foreground">
        Couldn&apos;t check the GST record. Type the names yourself.
      </p>
    );
  }

  const record = lookup.data;
  if (!record.valid) {
    return (
      <p className="text-xs text-danger">
        {record.reason ?? "This GSTIN doesn't check out. Look at it again."}
      </p>
    );
  }
  if (record.lookup === "unavailable") {
    return (
      <p className="text-xs text-muted-foreground">
        GST details can&apos;t be fetched yet. Type the names yourself.
      </p>
    );
  }
  const fill = gstinFillOf(record);
  if (record.lookup === "not_found" || fill === null) {
    return (
      <p className="text-xs text-muted-foreground">
        No GST record found for this GSTIN. Type the names yourself.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {record.legalName === null ? null : (
          <>
            <dt className="text-muted-foreground">Legal name</dt>
            <dd className="text-foreground">{record.legalName}</dd>
          </>
        )}
        {record.tradeName === null ? null : (
          <>
            <dt className="text-muted-foreground">Trade name</dt>
            <dd className="text-foreground">{record.tradeName}</dd>
          </>
        )}
        {record.status === null ? null : (
          <>
            <dt className="text-muted-foreground">Status</dt>
            <dd className="text-foreground">{record.status}</dd>
          </>
        )}
      </dl>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => {
          onUse(fill);
        }}
      >
        Use these details
      </Button>
    </div>
  );
}

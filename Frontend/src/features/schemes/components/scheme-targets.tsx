"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon } from "@/components/ui/icon";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { targetNameQueryOptions } from "@/features/schemes/api/schemes.queries";
import {
  PARTNER_TYPES,
  TARGET_TYPES,
  type SchemeTarget,
  type TargetType,
} from "@/features/schemes/api/schemes.schemas";
import { PARTNER_TYPE_LABELS, TARGET_TYPE_LABELS } from "@/features/schemes/lib/scheme-labels";

import { PartnerSearchPicker, ProductSearchPicker } from "./record-pickers";

/** A target as the form keeps it: the name it was picked by, for showing it. */
export interface DraftTarget {
  readonly type: TargetType;
  readonly id: string;
  readonly name: string | null;
}

/** A target's name: its own when sent (BE-027), else read from its record. */
export function TargetName({ target }: { target: DraftTarget | SchemeTarget }): React.ReactNode {
  const known = target.name ?? null;
  const lookup =
    known === null &&
    (target.type === "territory" || target.type === "partner" || target.type === "product")
      ? target.type
      : null;
  const query = useQuery({
    ...targetNameQueryOptions(lookup ?? "territory", target.id),
    enabled: lookup !== null,
  });
  if (target.type === "partner_type") return PARTNER_TYPE_LABELS[target.id] ?? target.id;
  if (known !== null) return known;
  if (lookup !== null && typeof query.data === "string") return query.data;
  return `${TARGET_TYPE_LABELS[target.type]} ${target.id.slice(0, 8)}…`;
}

/** SCHM-001 · Who a scheme is for: everyone, or a line per kind of target. */
export function TargetsSummary({
  targets,
}: {
  targets: readonly (DraftTarget | SchemeTarget)[];
}): React.JSX.Element {
  if (targets.length === 0) {
    return <p className="text-sm text-foreground">Everyone</p>;
  }
  const kinds = TARGET_TYPES.filter((type) => targets.some((target) => target.type === type));
  return (
    <div className="flex flex-col gap-2">
      <dl className="flex flex-col gap-2">
        {kinds.map((type) => (
          <div key={type} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
            <dt className="w-36 shrink-0 text-sm text-muted-foreground">
              {TARGET_TYPE_LABELS[type]}
            </dt>
            <dd className="text-sm text-foreground">
              {targets
                .filter((target) => target.type === type)
                .map((target, index, all) => (
                  <span key={target.id}>
                    <TargetName target={target} />
                    {index < all.length - 2 ? ", " : index === all.length - 2 ? " or " : ""}
                  </span>
                ))}
            </dd>
          </div>
        ))}
      </dl>
      {kinds.length > 1 ? (
        <p className="text-xs text-muted-foreground">
          A dealer must match every line; any one name on a line will do.
        </p>
      ) : null}
    </div>
  );
}

const ADDABLE: readonly TargetType[] = ["territory", "partner_type", "partner", "product"];

/**
 * SCHM-002 · Who a scheme is for. Empty means everyone; the same kind of target means any of
 * them, different kinds mean all. A product category can't be picked until the backend lists
 * categories with their ids (BE-027).
 */
export function TargetsEditor({
  value,
  onChange,
  disabled = false,
}: {
  value: readonly DraftTarget[];
  onChange: (next: readonly DraftTarget[]) => void;
  disabled?: boolean;
}): React.JSX.Element {
  const [kind, setKind] = useState<TargetType>("territory");
  const add = (target: DraftTarget): void => {
    if (value.some((item) => item.type === target.type && item.id === target.id)) return;
    onChange([...value, target]);
  };
  const remove = (target: DraftTarget): void => {
    onChange(value.filter((item) => !(item.type === target.type && item.id === target.id)));
  };

  return (
    <div className="flex flex-col gap-3">
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">Everyone. Add targets to narrow it.</p>
      ) : (
        <ul className="flex flex-wrap gap-2" aria-label="Targets">
          {value.map((target) => (
            <li
              key={`${target.type}-${target.id}`}
              className="flex items-center gap-1 rounded-full border border-border py-0.5 pr-1 pl-3 text-sm text-foreground"
            >
              <span className="text-muted-foreground">{TARGET_TYPE_LABELS[target.type]}:</span>{" "}
              <TargetName target={target} />
              {disabled ? null : (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Remove ${target.type === "partner_type" ? (PARTNER_TYPE_LABELS[target.id] ?? target.id) : (target.name ?? TARGET_TYPE_LABELS[target.type])}`}
                  onClick={() => {
                    remove(target);
                  }}
                >
                  <Icon icon={Cancel01Icon} />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {disabled ? null : (
        <div className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-3">
          <RadioGroup<TargetType>
            aria-label="Kind of target to add"
            value={kind}
            onValueChange={setKind}
            className="flex flex-wrap gap-x-4 gap-y-2"
          >
            {ADDABLE.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={type} />
                {TARGET_TYPE_LABELS[type]}
              </label>
            ))}
          </RadioGroup>
          {kind === "territory" ? (
            <TerritoryPicker
              id="scheme-target-territory"
              value={null}
              levels={["state", "district", "taluka"]}
              placeholder="Add a state, district or taluka"
              onValueChange={(territory: TerritoryChoice | null) => {
                if (territory !== null) {
                  add({ type: "territory", id: territory.id, name: territory.name });
                }
              }}
            />
          ) : kind === "partner_type" ? (
            <div role="group" aria-label="Partner types" className="flex flex-wrap gap-4">
              {PARTNER_TYPES.map((type) => {
                const chosen = value.some(
                  (item) => item.type === "partner_type" && item.id === type,
                );
                return (
                  <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                    <Checkbox
                      checked={chosen}
                      onCheckedChange={(checked) => {
                        const target: DraftTarget = { type: "partner_type", id: type, name: null };
                        if (checked) add(target);
                        else remove(target);
                      }}
                    />
                    {PARTNER_TYPE_LABELS[type]}
                  </label>
                );
              })}
            </div>
          ) : kind === "partner" ? (
            <PartnerSearchPicker
              id="scheme-target-partner"
              onPick={(record) => {
                add({ type: "partner", id: record.id, name: record.name });
              }}
            />
          ) : (
            <ProductSearchPicker
              id="scheme-target-product"
              onPick={(record) => {
                add({ type: "product", id: record.id, name: record.name });
              }}
            />
          )}
          <p className="text-xs text-muted-foreground">
            A partner also covers the dealers under it; a territory, everything inside it. Product
            categories can be added once the backend lists them with their ids (BE-027).
          </p>
        </div>
      )}
    </div>
  );
}

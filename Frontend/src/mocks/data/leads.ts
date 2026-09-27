import {
  leadWireSchema,
  type LeadInquiryType,
  type LeadPriority,
  type LeadStage,
  type LeadWire,
} from "@/features/leads/api/leads.schemas";

import { mockLookupCodes, mockLookupRows } from "./lookups";
import { createRandom, type Random } from "./random";
import {
  FIRST_NAMES,
  LAST_NAMES,
  LOST_NOTES,
  MOCK_ID_SPACE,
  MOCK_PARTNERS,
  MOCK_STAFF,
  MOCK_TALUKAS,
  mockUuid,
} from "./reference";
import { MOCK_TERRITORIES, mockOfficeFor, toTerritoryRef, type MockTerritory } from "./territories";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** Weighted so the pipeline looks like a real funnel. */
const STAGE_WEIGHTS: readonly (readonly [LeadStage, number])[] = [
  ["new", 20],
  ["contacted", 19],
  ["qualified", 15],
  ["quoted", 12],
  ["negotiation", 8],
  ["won", 11],
  ["lost", 8],
  ["dormant", 4],
  ["merged", 3],
];

/** Mostly drip, as in the client's order book. */
const MIS_WEIGHTS: readonly (readonly [string, number])[] = [
  ["drip", 60],
  ["mini_sprinkler", 15],
  ["sprinkler", 15],
  ["automation", 5],
  ["other", 5],
];

/** The backend's seeded thresholds (lead_score_rule): hot from 70, warm from 40. */
function priorityFor(score: number): LeadPriority {
  return score >= 70 ? "hot" : score >= 40 ? "warm" : "cold";
}

function pickWeighted<T>(random: Random, weights: readonly (readonly [T, number])[]): T {
  const total = weights.reduce((sum, [, weight]) => sum + weight, 0);
  let roll = random.next() * total;
  for (const [value, weight] of weights) {
    roll -= weight;
    if (roll <= 0) {
      return value;
    }
  }
  const [first] = weights;
  if (first === undefined) {
    throw new Error("pickWeighted() needs weights");
  }
  return first[0];
}

/** Rupees as the API sends them: a decimal string. */
function estimateValue(random: Random, type: LeadInquiryType, acreage: number): string | null {
  if (random.chance(0.1)) {
    return null;
  }
  const rupees =
    type === "subsidised"
      ? Math.round(acreage * random.int(55, 95)) * 1000
      : type === "commercial"
        ? random.int(5, 60) * 100_000
        : random.int(12, 90) * 100_000;
  return `${String(rupees)}.00`;
}

/**
 * Territories leads are placed in: talukas of the worked districts, and districts an office
 * covers (a lead in the uncovered district could never have been created).
 */
function territoryPool(): { talukas: MockTerritory[]; districts: MockTerritory[] } {
  return {
    talukas: MOCK_TERRITORIES.filter((territory) => territory.level === "taluka"),
    districts: MOCK_TERRITORIES.filter(
      (territory) => territory.level === "district" && mockOfficeFor(territory) !== null,
    ),
  };
}

function villageIn(random: Random, taluka: MockTerritory): string | null {
  const district = taluka.district ?? "";
  const villages = MOCK_TALUKAS[district]?.[taluka.name] ?? [];
  return villages.length > 0 && random.chance(0.85) ? random.pick(villages) : null;
}

/**
 * Deterministic mock leads in the backend's wire format, checked against the contract
 * (leadWireSchema). Dates are relative to `now`, so the demo always looks current. Every
 * 23rd lead shares its mobile number with the lead before it, and both carry the pending
 * duplicate link the backend would add.
 */
export function generateLeads(
  count = 137,
  seed = 20_260_914,
  now: number = Date.now(),
): LeadWire[] {
  const random = createRandom(seed);
  const sources = mockLookupCodes("lead-sources");
  const lostReasons = mockLookupRows("lost-reasons");
  const { talukas, districts } = territoryPool();
  const leads: LeadWire[] = [];

  for (let index = 0; index < count; index += 1) {
    const stage = pickWeighted(random, STAGE_WEIGHTS);
    const type: LeadInquiryType = random.chance(0.55)
      ? "subsidised"
      : random.pick(["commercial", "industrial"] as const);
    const inTaluka = random.chance(0.75);
    const territory = inTaluka ? random.pick(talukas) : random.pick(districts);
    const office = mockOfficeFor(territory);
    if (office === null) {
      throw new Error(`No mock office covers ${territory.name}`);
    }
    const owner = random.chance(0.85) ? random.pick(MOCK_STAFF) : null;
    const localPartners = MOCK_PARTNERS.filter(
      (partner) => partner.district === territory.district,
    );
    const partner =
      localPartners.length > 0 && random.chance(0.4) ? random.pick(localPartners) : null;
    const createdAt = now - random.int(1, 120) * DAY - random.int(0, 23) * HOUR;
    const lastActivityAt = Math.min(now, createdAt + random.int(0, 30) * DAY);
    const scored = random.chance(0.95);
    const score = random.int(8, 96);
    const first = random.pick(FIRST_NAMES);
    const last = random.pick(LAST_NAMES);
    const previous = leads.at(-1);
    const duplicateOfPrevious = previous !== undefined && index % 23 === 7;
    const reason = random.pick(lostReasons);

    const lead: LeadWire = {
      id: mockUuid(MOCK_ID_SPACE.lead, index + 1),
      inquiry_no: `POL/GJ/2026-27/${String(123 + index).padStart(5, "0")}`,
      stage,
      inquiry_type: type,
      mis_system: pickWeighted(random, MIS_WEIGHTS),
      source: random.pick(sources),
      farmer_name: `${first} ${last}`,
      mobile:
        duplicateOfPrevious && previous
          ? previous.mobile
          : `+91${random.pick(["9", "8", "7", "6"])}${String(random.int(100_000_000, 999_999_999))}`,
      email: random.chance(0.25)
        ? `${first.toLowerCase()}.${last.toLowerCase()}${String(index)}@example.com`
        : null,
      territory: toTerritoryRef(territory),
      village: inTaluka ? villageIn(random, territory) : null,
      owner,
      owner_org_unit: office,
      assigned_partner: partner
        ? { id: partner.id, name: partner.name, partner_type: partner.partner_type }
        : null,
      score: scored ? `${String(score)}.00` : null,
      priority: scored ? priorityFor(score) : null,
      estimated_value: estimateValue(random, type, random.int(1, 25)),
      lost_reason:
        stage === "lost" ? { id: reason.id, code: reason.code, name: reason.name } : null,
      lost_note: stage === "lost" && random.chance(0.5) ? random.pick(LOST_NOTES) : null,
      reopen_count: random.chance(0.05) ? 1 : 0,
      merged_into:
        stage === "merged" && previous
          ? { id: previous.id, inquiry_no: previous.inquiry_no }
          : null,
      first_contacted_at:
        stage === "new" ? null : new Date(createdAt + random.int(1, 48) * HOUR).toISOString(),
      last_activity_at: new Date(lastActivityAt).toISOString(),
      created_at: new Date(createdAt).toISOString(),
      created_by: owner ?? random.pick(MOCK_STAFF),
      duplicates: [],
    };

    if (duplicateOfPrevious && previous) {
      const linkId = mockUuid(MOCK_ID_SPACE.duplicate, index);
      lead.duplicates = [
        {
          link_id: linkId,
          lead_id: previous.id,
          inquiry_no: previous.inquiry_no,
          signal: "mobile",
          score: "1.00",
          state: "pending",
        },
      ];
      previous.duplicates = [
        ...(previous.duplicates ?? []),
        {
          link_id: linkId,
          lead_id: lead.id,
          inquiry_no: lead.inquiry_no,
          signal: "mobile",
          score: "1.00",
          state: "pending",
        },
      ];
    }

    leads.push(lead);
  }

  // Newest first, as the backend lists them; every lead must satisfy the contract.
  return leads
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id))
    .map((lead) => leadWireSchema.parse(lead));
}

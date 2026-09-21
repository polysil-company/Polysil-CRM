import {
  leadSchema,
  LEAD_SOURCES,
  ORDER_TYPES,
  type Lead,
  type LeadStatus,
  type OrderType,
} from "@/features/leads/api/leads.schemas";

import { createRandom, type Random } from "./random";
import {
  CHANNEL_PARTNERS,
  CROPS,
  FIRST_NAMES,
  LAST_NAMES,
  LOCATIONS,
  LOST_REASONS,
  OWNERS,
} from "./reference";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

/** Weighted so the pipeline looks like a real funnel. */
const STATUS_WEIGHTS: readonly (readonly [LeadStatus, number])[] = [
  ["new", 22],
  ["contacted", 20],
  ["qualified", 16],
  ["quoted", 13],
  ["negotiation", 9],
  ["won", 12],
  ["lost", 8],
];

const PROBABILITY_RANGE: Readonly<Record<LeadStatus, readonly [number, number]>> = {
  new: [10, 25],
  contacted: [20, 40],
  qualified: [40, 60],
  quoted: [55, 75],
  negotiation: [65, 90],
  won: [100, 100],
  lost: [0, 0],
};

function pickStatus(random: Random): LeadStatus {
  const total = STATUS_WEIGHTS.reduce((sum, [, weight]) => sum + weight, 0);
  let roll = random.next() * total;
  for (const [status, weight] of STATUS_WEIGHTS) {
    roll -= weight;
    if (roll <= 0) {
      return status;
    }
  }
  return "new";
}

function estimateValue(random: Random, type: OrderType, acreage: number): number | null {
  switch (type) {
    case "subsidised":
      return Math.round(acreage * random.int(55, 95)) * 1000;
    case "commercial":
      return random.int(5, 60) * 100_000;
    case "industrial":
      return random.int(12, 90) * 100_000;
    case "export":
      return random.int(20, 200) * 100_000;
    case "complaint":
      return random.chance(0.5) ? random.int(5, 40) * 1000 : null;
  }
}

function engagementSeries(random: Random, status: LeadStatus): number[] {
  const rising = status === "negotiation" || status === "quoted" || status === "won";
  return Array.from({ length: 12 }, (_, week) => {
    const base = rising ? Math.round(week * 0.6) : Math.max(0, 5 - Math.round(week * 0.3));
    return Math.max(0, base + random.int(0, 3));
  });
}

/**
 * Deterministic mock leads, validated against the real contract (leadSchema).
 * Dates are relative to `now`, so the demo always looks current.
 */
export function generateLeads(count = 137, seed = 20_260_914, now: number = Date.now()): Lead[] {
  const random = createRandom(seed);

  return Array.from({ length: count }, (_, index) => {
    const location = random.pick(LOCATIONS);
    const status = pickStatus(random);
    const type = random.chance(0.55) ? "subsidised" : random.pick(ORDER_TYPES);
    const acreage = random.int(1, 25);
    const createdAt = now - random.int(1, 120) * DAY - random.int(0, 23) * HOUR;
    const lastActivityAt = Math.min(now, createdAt + random.int(0, 30) * DAY);
    const open = status !== "won" && status !== "lost";
    const [minProbability, maxProbability] = PROBABILITY_RANGE[status];

    return leadSchema.parse({
      id: `lead-${String(10_001 + index)}`,
      code: `LD-26-${String(10_001 + index)}`,
      customerName: `${random.pick(FIRST_NAMES)} ${random.pick(LAST_NAMES)}`,
      phone: `+91${random.pick(["9", "8", "7", "6"])}${String(random.int(100_000_000, 999_999_999))}`,
      village: random.chance(0.85) ? random.pick(location.villages) : null,
      district: location.district,
      state: location.state,
      source: random.pick(LEAD_SOURCES),
      type,
      status,
      estimatedValue: estimateValue(random, type, acreage),
      winProbability: random.int(minProbability, maxProbability),
      crops: random.sample(CROPS, random.int(1, 4)),
      acreage,
      owner: random.pick(OWNERS),
      channelPartner: random.chance(0.6) ? random.pick(CHANNEL_PARTNERS) : null,
      engagement: engagementSeries(random, status),
      followUpAt: open
        ? new Date(now + random.int(-6, 12) * DAY + random.int(1, 8) * HOUR).toISOString()
        : null,
      lastActivityAt: new Date(lastActivityAt).toISOString(),
      lostReason: status === "lost" ? random.pick(LOST_REASONS) : null,
      createdAt: new Date(createdAt).toISOString(),
      updatedAt: new Date(lastActivityAt).toISOString(),
    });
  });
}

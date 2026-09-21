export interface Random {
  /** Float in [0, 1). */
  next: () => number;
  /** Integer in [min, max], inclusive. */
  int: (min: number, max: number) => number;
  pick: <T>(items: readonly T[]) => T;
  chance: (probability: number) => boolean;
  /** `count` distinct items. */
  sample: <T>(items: readonly T[], count: number) => T[];
}

/**
 * Deterministic generator (mulberry32): the same seed produces the same mock
 * data on every machine, so screenshots, bug reports and tests line up.
 */
export function createRandom(seed: number): Random {
  let state = seed >>> 0;

  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };

  const pick = <T>(items: readonly T[]): T => {
    const item = items[Math.floor(next() * items.length)];
    if (item === undefined) {
      throw new Error("pick() needs a non-empty list");
    }
    return item;
  };

  return {
    next,
    int: (min, max) => Math.floor(next() * (max - min + 1)) + min,
    pick,
    chance: (probability) => next() < probability,
    sample: (items, count) => {
      const pool = [...items];
      const result = [];
      while (result.length < count && pool.length > 0) {
        const index = Math.floor(next() * pool.length);
        const [item] = pool.splice(index, 1);
        if (item !== undefined) {
          result.push(item);
        }
      }
      return result;
    },
  };
}

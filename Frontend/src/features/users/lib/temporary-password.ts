/**
 * ADMN-003, ADMN-005 · A temporary password for a new person or a reset: four groups of four
 * from letters and digits that can't be misread (no 0/O, 1/l/I), e.g. `Kp7m-Rq4x-Tz9w-Hb3n`.
 * Nineteen characters, over the backend's minimum of twelve, and easy to read out by phone.
 * Drawn from the browser's cryptographic source, never `Math.random`.
 */

const ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const GROUPS = 4;
const GROUP_LENGTH = 4;

export function generateTemporaryPassword(): string {
  const values = new Uint32Array(GROUPS * GROUP_LENGTH);
  crypto.getRandomValues(values);
  const characters = [...values].map((value) => ALPHABET[value % ALPHABET.length] ?? "x");
  const groups: string[] = [];
  for (let index = 0; index < GROUPS; index += 1) {
    groups.push(characters.slice(index * GROUP_LENGTH, (index + 1) * GROUP_LENGTH).join(""));
  }
  return groups.join("-");
}

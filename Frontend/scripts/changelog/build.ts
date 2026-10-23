/**
 * Generates CHANGELOG.md from changelog/entries/ (REPO-001).
 *
 *   npm run changelog:build              write CHANGELOG.md
 *   npm run changelog:build -- --check   fail when CHANGELOG.md is out of date (CI)
 */

import { parseArgs } from "node:util";

import { loadEntries, readRepoFile, writeRepoFile } from "./io";
import { CHANGELOG_FILE, normalizeNewlines, renderChangelog } from "./lib";

function main(): number {
  const { values } = parseArgs({ options: { check: { type: "boolean", default: false } } });

  const { entries, invalid } = loadEntries();
  if (invalid.length > 0) {
    const count =
      invalid.length === 1 ? "1 changelog entry is" : `${invalid.length} changelog entries are`;
    console.error(`✕ ${count} invalid. Run npm run changelog:check to see why.`);
    return 1;
  }

  const next = renderChangelog(entries);
  const current = readRepoFile(CHANGELOG_FILE);
  const upToDate = current !== null && normalizeNewlines(current) === next;

  if (values.check) {
    if (!upToDate) {
      console.error(
        `✕ ${CHANGELOG_FILE} is out of date. Run npm run changelog:build and commit the result.`,
      );
      return 1;
    }
    console.log(`✓ ${CHANGELOG_FILE} is up to date.`);
    return 0;
  }

  if (!upToDate) {
    writeRepoFile(CHANGELOG_FILE, next);
  }
  const total = entries.length === 1 ? "1 entry" : `${entries.length} entries`;
  console.log(`✓ ${CHANGELOG_FILE} ${upToDate ? "was already up to date" : "written"} (${total}).`);
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`✕ ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}

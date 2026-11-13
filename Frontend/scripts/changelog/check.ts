/**
 * Validates changelog entries (REPO-001).
 *
 *   npm run changelog:check                         every entry is valid
 *   npm run changelog:check -- --staged             …and the staged commit includes an entry (pre-commit)
 *   npm run changelog:check -- --base origin/main   …and the branch includes an entry (CI)
 */

import { parseArgs } from "node:util";

import { changesSince, loadEntries, stagedChanges } from "./io";
import { ENTRIES_DIR, evaluateChanges, type FileChange } from "./lib";

const MISSING_ENTRY = [
  "✕ This change has no changelog entry.",
  "  Every change adds or updates a file in changelog/entries/. Create one with:",
  '    npm run changelog:new -- --type fix --data-id LEAD-002 --title "What changed, in plain language"',
  "  Fill in Before, Now, Discussion, Files changed and Tests, then stage it with your change.",
].join("\n");

function readChanges(options: {
  readonly staged: boolean;
  readonly base: string | undefined;
}): FileChange[] | null {
  if (options.base !== undefined) {
    return changesSince(options.base);
  }
  return options.staged ? stagedChanges() : null;
}

function main(): number {
  const { values } = parseArgs({
    options: {
      staged: { type: "boolean", default: false },
      base: { type: "string" },
    },
  });

  const { entries, invalid } = loadEntries();
  for (const entry of invalid) {
    console.error(`✕ ${ENTRIES_DIR}/${entry.file}`);
    for (const problem of entry.problems) {
      console.error(`    ${problem}`);
    }
  }

  let missingEntry = false;
  const changes = readChanges({ staged: values.staged, base: values.base });
  if (changes !== null) {
    const { needsEntry, entryFiles } = evaluateChanges(changes);
    missingEntry = needsEntry && entryFiles.length === 0;
  }
  if (missingEntry) {
    console.error(MISSING_ENTRY);
  }

  if (invalid.length > 0 || missingEntry) {
    return 1;
  }

  console.log(
    `✓ ${entries.length} changelog ${entries.length === 1 ? "entry is" : "entries are"} valid.`,
  );
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`✕ ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}

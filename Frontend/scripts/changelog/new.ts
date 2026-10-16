/**
 * Creates a changelog entry from changelog/TEMPLATE.md (REPO-001).
 *
 *   npm run changelog:new -- --type feature --data-id LEAD-002 --title "Create a lead from a dialog"
 *   npm run changelog:new -- -t fix -d LEAD-001 -d LEAD-004 --title "…" --slug short-name --breaking
 */

import { parseArgs } from "node:util";

import { gitUserName, readRepoFile, writeRepoFile } from "./io";
import {
  CHANGE_TYPES,
  createEntrySource,
  describeIssues,
  ENTRIES_DIR,
  entryFileName,
  entryFrontmatterSchema,
  istDate,
  slugify,
  TEMPLATE_FILE,
} from "./lib";

const USAGE = [
  "Usage:",
  `  npm run changelog:new -- --type <${CHANGE_TYPES.join("|")}> --data-id <DATA-ID> --title "<title>"`,
  '  Optional: repeat --data-id for more IDs, --slug <short-name>, --breaking, --author "<name>"',
].join("\n");

function main(): number {
  const { values } = parseArgs({
    options: {
      type: { type: "string", short: "t" },
      "data-id": { type: "string", short: "d", multiple: true },
      title: { type: "string" },
      slug: { type: "string" },
      author: { type: "string" },
      breaking: { type: "boolean", default: false },
    },
  });

  const meta = entryFrontmatterSchema.safeParse({
    date: istDate(),
    type: values.type,
    title: values.title,
    dataIds: values["data-id"] ?? [],
    author: values.author ?? gitUserName() ?? "",
    breaking: values.breaking,
  });

  if (!meta.success) {
    console.error(USAGE);
    for (const line of describeIssues(meta.error)) {
      console.error(`✕ ${line}`);
    }
    return 1;
  }

  const slug = slugify(values.slug ?? meta.data.title);
  const [primaryDataId] = meta.data.dataIds;
  if (slug.length === 0 || primaryDataId === undefined) {
    console.error("✕ Could not build a file name from the title. Pass --slug short-name.");
    return 1;
  }

  const file = entryFileName({
    date: meta.data.date,
    type: meta.data.type,
    dataId: primaryDataId,
    slug,
  });
  const target = `${ENTRIES_DIR}/${file}`;
  if (readRepoFile(target) !== null) {
    console.error(`✕ ${target} already exists. Edit it, or pass a different --slug.`);
    return 1;
  }

  const template = readRepoFile(TEMPLATE_FILE);
  if (template === null) {
    console.error(`✕ ${TEMPLATE_FILE} is missing.`);
    return 1;
  }

  writeRepoFile(target, createEntrySource(meta.data, template));
  console.log(`✓ Created ${target}`);
  console.log(
    "  Fill in Before, Now, Discussion, Files changed and Tests, then stage it with your change.",
  );
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  console.error(`✕ ${error instanceof Error ? error.message : String(error)}`);
  console.error(USAGE);
  process.exitCode = 1;
}

import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";
import { stringify } from "yaml";

import {
  createEntrySource,
  evaluateChanges,
  formatEntryDate,
  istDate,
  parseEntry,
  parseNameStatus,
  renderChangelog,
  slugify,
  splitFrontmatter,
  TEMPLATE_FILE,
  type ChangelogEntry,
  type EntryFrontmatter,
} from "./lib";

const FILE = "2026-09-14--feature--LEAD-002--new-lead-dialog.md";

const META: EntryFrontmatter = {
  date: "2026-09-14",
  type: "feature",
  title: "New lead dialog",
  dataIds: ["LEAD-002"],
  author: "Test Author",
  breaking: false,
};

const BODY = `## Before

Leads could only be imported from a spreadsheet.

## Now

Staff create a lead from a dialog.

### Validation

Phone numbers are checked before the request is sent.

## Discussion

A dialog keeps the list in view.

## Files changed

- \`src/features/leads/components/new-lead-dialog.tsx\` — new

## Tests

- \`leads-ui.test.tsx\` — [LEAD-002] NewLeadDialog
`;

function source(meta: Record<string, unknown> = {}, body = BODY): string {
  return `---\n${stringify({ ...META, ...meta })}---\n\n${body}`;
}

function parse(file: string, text: string): ChangelogEntry {
  const result = parseEntry(file, text);
  if (!result.ok) {
    throw new Error(result.problems.join("\n"));
  }
  return result.entry;
}

function problems(file: string, text: string): readonly string[] {
  const result = parseEntry(file, text);
  return result.ok ? [] : result.problems;
}

describe("[REPO-001] changelog entry validation", () => {
  it("parses a complete entry", () => {
    const entry = parse(FILE, source());

    expect(entry.meta).toEqual(META);
    expect(entry.sections.map((section) => section.heading)).toEqual([
      "Before",
      "Now",
      "Discussion",
      "Files changed",
      "Tests",
    ]);
  });

  it("explains a badly named file", () => {
    expect(problems("new-lead-dialog.md", source())).toEqual([
      expect.stringContaining("File name must look like"),
    ]);
  });

  it("requires the file name to agree with the frontmatter", () => {
    expect(problems("2026-09-15--fix--LEAD-001--new-lead-dialog.md", source())).toEqual([
      "File name date 2026-09-15 does not match the frontmatter date 2026-09-14",
      "File name type fix does not match the frontmatter type feature",
      "File name Data ID LEAD-001 must be the first item in dataIds",
    ]);
  });

  it("rejects unknown change types, unregistered Data IDs and malformed dates", () => {
    const found = problems(
      FILE,
      source({ type: "feat", dataIds: ["LEAD-002", "LEAD-999"], date: "14-09-2026" }),
    );

    expect(found).toEqual(
      expect.arrayContaining([
        expect.stringContaining("Use one of: feature, fix"),
        expect.stringContaining("LEAD-999 is not registered"),
        expect.stringContaining("Use the date as YYYY-MM-DD"),
      ]),
    );
  });

  it("requires every section and does not count template comments as content", () => {
    const body = [
      "## Before",
      "x",
      "## Now",
      "y",
      "## Discussion",
      "<!-- Why this approach? -->",
      "## Files changed",
      "- a",
    ].join("\n\n");

    expect(problems(FILE, source({}, body))).toEqual([
      'Fill in the "## Discussion" section',
      'Add a "## Tests" section',
    ]);
  });

  it("treats headings inside code fences as content", () => {
    const body = BODY.replace(
      "## Tests\n\n- `leads-ui.test.tsx` — [LEAD-002] NewLeadDialog\n",
      "```md\n## Tests\n```\n",
    );

    expect(problems(FILE, source({}, body))).toEqual(['Add a "## Tests" section']);
  });

  it("reports missing frontmatter and invalid YAML", () => {
    expect(problems(FILE, BODY)).toEqual([
      "Start the file with YAML frontmatter between two --- lines",
    ]);
    expect(problems(FILE, `---\ntitle: [unclosed\n---\n\n${BODY}`)).toEqual([
      expect.stringContaining("Frontmatter is not valid YAML"),
    ]);
  });

  it("accepts Windows line endings", () => {
    expect(parseEntry(FILE, source().replace(/\n/g, "\r\n")).ok).toBe(true);
  });
});

describe("[REPO-001] CHANGELOG.md rendering", () => {
  const newer = parse(FILE, source({ breaking: true }));
  const older = parse(
    "2026-09-13--fix--LEAD-001--older-fix.md",
    source({
      date: "2026-09-13",
      type: "fix",
      title: "Older fix",
      dataIds: ["LEAD-001", "LEAD-004"],
    }),
  );

  it("lists dates newest first, whatever order the entries arrive in", () => {
    const output = renderChangelog([older, newer]);

    expect(output).toBe(renderChangelog([newer, older]));
    expect(output.indexOf("## 14 September 2026")).toBeLessThan(
      output.indexOf("## 13 September 2026"),
    );
  });

  it("renders the metadata line, the breaking notice and every section", () => {
    const output = renderChangelog([newer]);

    expect(output).toContain("### New lead dialog");
    expect(output).toContain(
      `\`feature\` · \`LEAD-002\` · Test Author · [entry](changelog/entries/${FILE})`,
    );
    expect(output).toContain("> **Breaking change.**");
    expect(output).toContain("#### Files changed");
  });

  it("nests an entry's own headings under its section", () => {
    expect(renderChangelog([newer])).toContain("\n##### Validation\n");
  });

  it("opens with an index, one row per change, newest first, each linking to its entry", () => {
    const output = renderChangelog([older, newer]);

    expect(output).toContain("## Index\n\n2 changes, newest first.");
    expect(output).toContain(
      `| 2026-09-14 | [New lead dialog](changelog/entries/${FILE}) **(breaking)** | \`feature\` | \`LEAD-002\` |`,
    );
    expect(output.indexOf("| 2026-09-14 |")).toBeLessThan(output.indexOf("| 2026-09-13 |"));
    expect(output.indexOf("## Index")).toBeLessThan(output.indexOf("## 14 September 2026"));
  });

  it("says so when there are no entries", () => {
    expect(renderChangelog([])).toContain("_No entries yet._");
  });

  it("formats dates without depending on the machine's locale", () => {
    expect(formatEntryDate("2026-09-04")).toBe("4 September 2026");
  });
});

describe("[REPO-001] change sets", () => {
  it("parses git name-status output", () => {
    expect(parseNameStatus("M\0src/app/page.tsx\0A\0changelog/entries/x.md\0D\0old.ts\0")).toEqual([
      { status: "M", path: "src/app/page.tsx" },
      { status: "A", path: "changelog/entries/x.md" },
      { status: "D", path: "old.ts" },
    ]);
  });

  it("requires an entry when code changes", () => {
    expect(evaluateChanges([{ status: "M", path: "src/app/page.tsx" }])).toEqual({
      needsEntry: true,
      entryFiles: [],
    });
  });

  it("accepts a change that adds or edits an entry, but not one that deletes it", () => {
    const code = { status: "M", path: "src/app/page.tsx" };
    const entry = `changelog/entries/${FILE}`;

    expect(evaluateChanges([code, { status: "A", path: entry }]).entryFiles).toEqual([entry]);
    expect(evaluateChanges([code, { status: "M", path: entry }]).entryFiles).toEqual([entry]);
    expect(evaluateChanges([code, { status: "D", path: entry }]).entryFiles).toEqual([]);
  });

  it("does not require an entry for changelog-only changes", () => {
    expect(evaluateChanges([{ status: "M", path: "CHANGELOG.md" }]).needsEntry).toBe(false);
    expect(evaluateChanges([]).needsEntry).toBe(false);
  });
});

describe("[REPO-001] new entries", () => {
  it("builds a short, safe slug from a title", () => {
    expect(slugify("Create a lead — from a dialog!")).toBe("create-a-lead-from-a-dialog");
    expect(slugify("Café pricing")).toBe("cafe-pricing");
    expect(slugify(`${"a".repeat(30)} ${"b".repeat(40)}`)).toBe("a".repeat(30));
  });

  it("uses today's date in India", () => {
    expect(istDate(new Date("2026-09-14T18:29:00Z"))).toBe("2026-09-14");
    expect(istDate(new Date("2026-09-14T18:30:00Z"))).toBe("2026-09-15");
  });

  it("creates an entry from the real template that fails until its sections are filled", () => {
    const template = readFileSync(path.resolve(TEMPLATE_FILE), "utf8");
    const created = createEntrySource(META, template);

    expect(splitFrontmatter(created)?.yaml).toContain("title: New lead dialog");
    expect(problems(FILE, created)).toEqual([
      'Fill in the "## Before" section',
      'Fill in the "## Now" section',
      'Fill in the "## Discussion" section',
      'Fill in the "## Files changed" section',
      'Fill in the "## Tests" section',
    ]);
  });
});

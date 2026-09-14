/**
 * Changelog entries — parse, validate and render (REPO-001).
 *
 * Every change ships with one Markdown entry in changelog/entries/ that records
 * Before, Now, Discussion, Files changed and Tests. CHANGELOG.md is generated
 * from the entries and is never edited by hand.
 *
 * Everything in this module is pure — no file system, no git — so it is unit
 * tested. File and git access live in ./io.ts. Author rules: changelog/README.md.
 */

import { parse as parseYaml, stringify as stringifyYaml } from "yaml";
import { z } from "zod";

import { isDataId } from "@/lib/data-ids";

export const ENTRIES_DIR = "changelog/entries";
export const TEMPLATE_FILE = "changelog/TEMPLATE.md";
export const CHANGELOG_FILE = "CHANGELOG.md";

export const CHANGE_TYPES = [
  "feature",
  "fix",
  "api-integration",
  "design",
  "refactor",
  "performance",
  "security",
  "docs",
  "test",
  "chore",
] as const;

export type ChangeType = (typeof CHANGE_TYPES)[number];

/** Every entry fills these `## ` sections. Extra sections are allowed and rendered after them. */
export const REQUIRED_SECTIONS = ["Before", "Now", "Discussion", "Files changed", "Tests"] as const;

/** `2026-09-14--feature--LEAD-002--new-lead-dialog.md` → date, type, primary Data ID, slug. */
export const ENTRY_FILE_PATTERN =
  /^(\d{4}-\d{2}-\d{2})--([a-z]+(?:-[a-z]+)*)--([A-Z]{2,6}-\d{3})--([a-z0-9]+(?:-[a-z0-9]+)*)\.md$/;

const EXAMPLE_FILE_NAME = "2026-09-14--feature--LEAD-002--new-lead-dialog.md";

export const entryFrontmatterSchema = z.object({
  date: z.iso.date({ error: "Use the date as YYYY-MM-DD" }),
  type: z.enum(CHANGE_TYPES, { error: `Use one of: ${CHANGE_TYPES.join(", ")}` }),
  title: z
    .string({ error: "Write a one-line title" })
    .trim()
    .min(3, "Write a one-line title")
    .max(120, "Keep the title under 120 characters"),
  dataIds: z
    .array(
      z.string().refine(isDataId, {
        error: (issue) =>
          `${String(issue.input)} is not registered in src/lib/data-ids/registry.ts`,
      }),
      { error: "List the Data IDs this change touches" },
    )
    .min(1, "List at least one Data ID")
    .refine((ids) => new Set(ids).size === ids.length, "List each Data ID once"),
  author: z.string({ error: "Add the author's name" }).trim().min(1, "Add the author's name"),
  breaking: z.boolean({ error: "Use true or false" }).default(false),
});

export type EntryFrontmatter = z.infer<typeof entryFrontmatterSchema>;

export interface EntrySection {
  readonly heading: string;
  readonly content: string;
}

export interface ChangelogEntry {
  /** File name inside changelog/entries/. */
  readonly file: string;
  readonly meta: EntryFrontmatter;
  /** `## ` sections in document order. */
  readonly sections: readonly EntrySection[];
}

export type EntryParseResult =
  | { readonly ok: true; readonly entry: ChangelogEntry }
  | { readonly ok: false; readonly file: string; readonly problems: readonly string[] };

export interface FileChange {
  /** Git status letter: A added, M modified, D deleted, T type changed. */
  readonly status: string;
  /** Repository-relative path with forward slashes. */
  readonly path: string;
}

export interface ChangeEvaluation {
  /** The change touches something other than the changelog itself. */
  readonly needsEntry: boolean;
  /** Entries the change adds or edits. */
  readonly entryFiles: readonly string[];
}

/* ── Parsing ───────────────────────────────────────────────────────────────── */

const FRONTMATTER_PATTERN = /^---\n([\s\S]*?)\n---(?:\n|$)([\s\S]*)$/;
const SECTION_HEADING_PATTERN = /^##[ \t]+(.+?)[ \t]*$/;
const FENCE_PATTERN = /^[ \t]*(?:```|~~~)/;
const HEADING_PATTERN = /^#{1,6}(?=[ \t])/;
const COMMENT_PATTERN = /<!--[\s\S]*?-->/g;

export function normalizeNewlines(text: string): string {
  return text.replace(/^﻿/, "").replace(/\r\n?/g, "\n");
}

export function splitFrontmatter(
  source: string,
): { readonly yaml: string; readonly body: string } | null {
  const match = FRONTMATTER_PATTERN.exec(normalizeNewlines(source));
  if (match === null) {
    return null;
  }
  return { yaml: match[1] ?? "", body: match[2] ?? "" };
}

/** Splits a Markdown body into its `## ` sections. Headings inside code fences are content. */
export function extractSections(body: string): EntrySection[] {
  const sections: { heading: string; lines: string[] }[] = [];
  let inFence = false;

  for (const line of normalizeNewlines(body).split("\n")) {
    const isFence = FENCE_PATTERN.test(line);
    const heading = inFence || isFence ? undefined : SECTION_HEADING_PATTERN.exec(line)?.[1];
    if (isFence) {
      inFence = !inFence;
    }

    if (heading === undefined) {
      sections.at(-1)?.lines.push(line);
    } else {
      sections.push({ heading, lines: [] });
    }
  }

  return sections.map(({ heading, lines }) => ({ heading, content: lines.join("\n").trim() }));
}

function isBlank(markdown: string): boolean {
  return markdown.replace(COMMENT_PATTERN, "").trim().length === 0;
}

function findSection(sections: readonly EntrySection[], heading: string): EntrySection | undefined {
  const wanted = heading.toLowerCase();
  return sections.find((section) => section.heading.toLowerCase() === wanted);
}

function sectionProblems(sections: readonly EntrySection[]): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();

  for (const { heading } of sections) {
    const key = heading.toLowerCase();
    if (seen.has(key)) {
      problems.push(`Section "## ${heading}" appears more than once`);
    }
    seen.add(key);
  }

  for (const required of REQUIRED_SECTIONS) {
    const section = findSection(sections, required);
    if (section === undefined) {
      problems.push(`Add a "## ${required}" section`);
    } else if (isBlank(section.content)) {
      problems.push(`Fill in the "## ${required}" section`);
    }
  }

  return problems;
}

/** One readable line per schema issue: `dataIds.1: LEAD-999 is not registered …`. */
export function describeIssues(error: z.ZodError): string[] {
  return error.issues.map((issue) => {
    const where = issue.path.length > 0 ? issue.path.map(String).join(".") : "(root)";
    return `${where}: ${issue.message}`;
  });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Parses and validates one entry, collecting every problem instead of stopping at the first. */
export function parseEntry(file: string, source: string): EntryParseResult {
  const problems: string[] = [];

  const nameParts = ENTRY_FILE_PATTERN.exec(file);
  if (nameParts === null) {
    problems.push(`File name must look like ${EXAMPLE_FILE_NAME}`);
  }

  const parts = splitFrontmatter(source);
  if (parts === null) {
    problems.push("Start the file with YAML frontmatter between two --- lines");
    return { ok: false, file, problems };
  }

  let raw: unknown;
  try {
    raw = parseYaml(parts.yaml);
  } catch (error) {
    problems.push(`Frontmatter is not valid YAML: ${errorMessage(error)}`);
    return { ok: false, file, problems };
  }

  const meta = entryFrontmatterSchema.safeParse(raw);
  if (!meta.success) {
    problems.push(...describeIssues(meta.error).map((line) => `Frontmatter ${line}`));
  }

  if (nameParts !== null && meta.success) {
    const [, date, type, dataId] = nameParts;
    if (date !== meta.data.date) {
      problems.push(`File name date ${date} does not match the frontmatter date ${meta.data.date}`);
    }
    if (type !== meta.data.type) {
      problems.push(`File name type ${type} does not match the frontmatter type ${meta.data.type}`);
    }
    if (dataId !== meta.data.dataIds[0]) {
      problems.push(`File name Data ID ${dataId} must be the first item in dataIds`);
    }
  }

  const sections = extractSections(parts.body);
  problems.push(...sectionProblems(sections));

  if (!meta.success || problems.length > 0) {
    return { ok: false, file, problems };
  }

  return { ok: true, entry: { file, meta: meta.data, sections } };
}

/* ── Rendering CHANGELOG.md ────────────────────────────────────────────────── */

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
] as const;

const CHANGELOG_HEADER = [
  "# Changelog",
  "",
  "<!-- Generated by `npm run changelog:build` from changelog/entries/. Do not edit this file by hand. -->",
  "",
  "Every change to this repository, newest first. Each entry records what existed before, what exists now, the discussion behind the change, the files it touched and how it is tested.",
  "How to write an entry: [changelog/README.md](changelog/README.md).",
  "",
];

/** `2026-09-04` → `4 September 2026`. Locale-independent, so every machine renders the same bytes. */
export function formatEntryDate(date: string): string {
  const [year = "", month = "", day = ""] = date.split("-");
  const monthName = MONTHS[Number(month) - 1] ?? month;
  return `${Number(day)} ${monthName} ${year}`;
}

function compareText(a: string, b: string): number {
  if (a === b) {
    return 0;
  }
  return a < b ? -1 : 1;
}

/** Newest date first; entries from the same day in file-name order. */
export function sortEntries(entries: readonly ChangelogEntry[]): ChangelogEntry[] {
  return [...entries].sort(
    (a, b) => compareText(b.meta.date, a.meta.date) || compareText(a.file, b.file),
  );
}

/** Shifts headings down so an entry's own headings nest under its section heading. */
function demoteHeadings(markdown: string, levels: number): string {
  let inFence = false;
  return markdown
    .split("\n")
    .map((line) => {
      if (FENCE_PATTERN.test(line)) {
        inFence = !inFence;
        return line;
      }
      if (inFence) {
        return line;
      }
      return line.replace(HEADING_PATTERN, (hashes) =>
        "#".repeat(Math.min(6, hashes.length + levels)),
      );
    })
    .join("\n");
}

/** Required sections in canonical order with canonical names, then any extra sections. */
function orderedSections(sections: readonly EntrySection[]): EntrySection[] {
  const required = REQUIRED_SECTIONS.flatMap((heading) => {
    const section = findSection(sections, heading);
    return section === undefined ? [] : [{ heading, content: section.content }];
  });
  const requiredKeys = new Set<string>(REQUIRED_SECTIONS.map((heading) => heading.toLowerCase()));
  const extra = sections.filter((section) => !requiredKeys.has(section.heading.toLowerCase()));
  return [...required, ...extra];
}

function renderEntry(entry: ChangelogEntry): string[] {
  const { meta } = entry;
  const dataIds = meta.dataIds.map((id) => `\`${id}\``).join(" ");
  const lines = [
    `### ${meta.title}`,
    "",
    `\`${meta.type}\` · ${dataIds} · ${meta.author} · [entry](${ENTRIES_DIR}/${entry.file})`,
    "",
  ];

  if (meta.breaking) {
    lines.push("> **Breaking change.** Read the discussion before you build on this.", "");
  }

  for (const section of orderedSections(entry.sections)) {
    const content = demoteHeadings(section.content.replace(COMMENT_PATTERN, "").trim(), 2);
    lines.push(`#### ${section.heading}`, "", content, "");
  }

  return lines;
}

/** Renders CHANGELOG.md. Deterministic: the same entries always produce the same bytes. */
export function renderChangelog(entries: readonly ChangelogEntry[]): string {
  const lines = [...CHANGELOG_HEADER];

  if (entries.length === 0) {
    lines.push("_No entries yet._");
  }

  let currentDate: string | null = null;
  for (const entry of sortEntries(entries)) {
    if (entry.meta.date !== currentDate) {
      currentDate = entry.meta.date;
      lines.push(`## ${formatEntryDate(currentDate)}`, "");
    }
    lines.push(...renderEntry(entry));
  }

  return `${lines.join("\n").trimEnd()}\n`;
}

/* ── Change sets — pre-commit and CI ───────────────────────────────────────── */

/** Parses `git diff --name-status --no-renames -z` output. */
export function parseNameStatus(output: string): FileChange[] {
  const fields = output.split("\0").filter((field) => field.length > 0);
  const changes: FileChange[] = [];
  for (let index = 0; index + 1 < fields.length; index += 2) {
    const status = fields[index];
    const path = fields[index + 1];
    if (status !== undefined && path !== undefined) {
      changes.push({ status: status.charAt(0), path });
    }
  }
  return changes;
}

function isChangelogPath(path: string): boolean {
  return path === CHANGELOG_FILE || path.startsWith("changelog/");
}

function isEntryPath(path: string): boolean {
  return path.startsWith(`${ENTRIES_DIR}/`) && path.endsWith(".md");
}

/** A change needs an entry when it touches anything outside the changelog itself. */
export function evaluateChanges(changes: readonly FileChange[]): ChangeEvaluation {
  return {
    needsEntry: changes.some((change) => !isChangelogPath(change.path)),
    entryFiles: changes
      .filter((change) => change.status !== "D" && isEntryPath(change.path))
      .map((change) => change.path),
  };
}

/* ── New entries ───────────────────────────────────────────────────────────── */

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/** Today's date in India (UTC+05:30, no daylight saving) as YYYY-MM-DD. */
export function istDate(now: Date = new Date()): string {
  return new Date(now.getTime() + IST_OFFSET_MS).toISOString().slice(0, 10);
}

/** "Create a lead — from a dialog!" → "create-a-lead-from-a-dialog", cut at a word boundary. */
export function slugify(text: string, maxLength = 60): string {
  const slug = text
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

  if (slug.length <= maxLength) {
    return slug;
  }
  const cut = slug.slice(0, maxLength);
  const lastDash = cut.lastIndexOf("-");
  return lastDash > 0 ? cut.slice(0, lastDash) : cut;
}

export function entryFileName(parts: {
  readonly date: string;
  readonly type: ChangeType;
  readonly dataId: string;
  readonly slug: string;
}): string {
  return `${parts.date}--${parts.type}--${parts.dataId}--${parts.slug}.md`;
}

/** A new entry: generated frontmatter followed by the template's sections. */
export function createEntrySource(meta: EntryFrontmatter, template: string): string {
  const body = splitFrontmatter(template)?.body ?? normalizeNewlines(template);
  return `---\n${stringifyYaml(meta)}---\n\n${body.trimStart()}`;
}

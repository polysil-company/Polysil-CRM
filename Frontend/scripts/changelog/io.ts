/**
 * File system and git access for the changelog scripts (REPO-001).
 *
 * The scripts run through npm, so the working directory is the project root — the folder
 * with package.json. That folder is either the repository root or a subfolder of a larger
 * repository, such as the Polysil-CRM monorepo. Git diffs therefore use --relative:
 * they list only files inside the project, with paths relative to it, so backend changes
 * never ask for a frontend changelog entry.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import {
  ENTRIES_DIR,
  parseEntry,
  parseNameStatus,
  type ChangelogEntry,
  type FileChange,
} from "./lib";

const PROJECT_ROOT = process.cwd();

export interface InvalidEntry {
  readonly file: string;
  readonly problems: readonly string[];
}

export interface LoadedEntries {
  readonly entries: readonly ChangelogEntry[];
  readonly invalid: readonly InvalidEntry[];
}

function repoPath(relativePath: string): string {
  return path.join(PROJECT_ROOT, relativePath);
}

export function readRepoFile(relativePath: string): string | null {
  const target = repoPath(relativePath);
  return existsSync(target) ? readFileSync(target, "utf8") : null;
}

export function writeRepoFile(relativePath: string, content: string): void {
  const target = repoPath(relativePath);
  mkdirSync(path.dirname(target), { recursive: true });
  writeFileSync(target, content, "utf8");
}

/** Reads and validates every entry in changelog/entries/. */
export function loadEntries(): LoadedEntries {
  const directory = repoPath(ENTRIES_DIR);
  const files = existsSync(directory)
    ? readdirSync(directory)
        .filter((file) => file.endsWith(".md"))
        .sort()
    : [];

  const entries: ChangelogEntry[] = [];
  const invalid: InvalidEntry[] = [];
  for (const file of files) {
    const result = parseEntry(file, readFileSync(path.join(directory, file), "utf8"));
    if (result.ok) {
      entries.push(result.entry);
    } else {
      invalid.push({ file: result.file, problems: result.problems });
    }
  }

  return { entries, invalid };
}

function git(args: readonly string[]): string {
  return execFileSync("git", args, { cwd: PROJECT_ROOT, encoding: "utf8" });
}

/** Files inside the project that are staged for the commit being created. */
export function stagedChanges(): FileChange[] {
  return parseNameStatus(
    git(["diff", "--cached", "--name-status", "--no-renames", "--relative", "-z"]),
  );
}

const GIT_REF_PATTERN = /^\w[\w./~^-]*$/;

/** Files inside the project changed on this branch since it forked from `base`, e.g. origin/main. */
export function changesSince(base: string): FileChange[] {
  if (!GIT_REF_PATTERN.test(base)) {
    throw new Error(`"${base}" is not a valid git ref`);
  }
  return parseNameStatus(
    git(["diff", "--name-status", "--no-renames", "--relative", "-z", `${base}...HEAD`]),
  );
}

/** The committer's name from git config — the default author of a new entry. */
export function gitUserName(): string | null {
  try {
    const name = git(["config", "user.name"]).trim();
    return name.length > 0 ? name : null;
  } catch {
    return null;
  }
}

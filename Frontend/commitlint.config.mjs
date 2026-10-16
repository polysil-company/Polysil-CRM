/**
 * Commit message rules.
 *
 * Format:  <type>(<scope>): <subject>
 * Example: feat(LEAD-002): add New Lead dialog with optimistic insert
 *
 * The scope is a Data ID (see Docs/Data-IDs.md) so every commit traces to a
 * functionality shared by frontend and backend. Work that genuinely has no
 * Data ID uses one of the generic scopes below.
 */

const DATA_ID_PATTERN = /^[A-Z]{2,6}-\d{3}$/;

const GENERIC_SCOPES = ["deps", "ci", "repo", "docs", "tooling", "release"];

/** @type {import('@commitlint/types').UserConfig} */
const config = {
  extends: ["@commitlint/config-conventional"],
  plugins: [
    {
      rules: {
        "scope-data-id": (parsed) => {
          const scope = parsed.scope ?? "";
          const parts = scope.split(",").map((part) => part.trim());
          const valid =
            scope.length > 0 &&
            parts.every((part) => DATA_ID_PATTERN.test(part) || GENERIC_SCOPES.includes(part));

          return [
            valid,
            `scope must be one or more Data IDs (e.g. "LEAD-002" or "LEAD-001,LEAD-002") or one of: ${GENERIC_SCOPES.join(", ")}`,
          ];
        },
      },
    },
  ],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "api",
        "design",
        "refactor",
        "perf",
        "test",
        "docs",
        "security",
        "chore",
        "ci",
        "build",
        "revert",
      ],
    ],
    "scope-empty": [2, "never"],
    "scope-case": [0],
    "scope-data-id": [2, "always"],
    "subject-case": [0],
    "header-max-length": [2, "always", 100],
  },
};

export default config;

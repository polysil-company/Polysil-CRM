# Changelog system

Every change to this repository ships with a changelog entry: one short Markdown file in [`entries/`](entries) that answers five questions.

| Section           | Answers                                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| **Before**        | What existed before, and what was wrong or missing?                                                          |
| **Now**           | What exists after the change? Behaviour, not code — including loading, empty, error, mobile and dark states. |
| **Discussion**    | Why this approach? What was rejected? Who decided, and when? What is left to do (with Data IDs)?             |
| **Files changed** | Which files changed, one line each. Group many similar files by folder.                                      |
| **Tests**         | Which tests cover the change, and how to check it by hand. No automated test? Say why.                       |

[`CHANGELOG.md`](../CHANGELOG.md) at the repository root is **generated** from the entries. Never edit it by hand. It opens with an **index** — one line per change: date, title (linking to its entry), type and Data IDs — then every entry in full, newest first. Nothing is appended to a long file: each change is its own entry, so no file grows without bound except the generated one, which is rebuilt from scratch every time.

What a user can do today, and how far each feature is tested, is in [Docs/Tested-Features.md](../Docs/Tested-Features.md).

## Write an entry

```bash
npm run changelog:new -- --type feature --data-id LEAD-002 --title "Create a lead from a dialog"
```

That creates `entries/2026-09-14--feature--LEAD-002--create-a-lead-from-a-dialog.md` from [`TEMPLATE.md`](TEMPLATE.md), with today's date in India and your `git config user.name` as the author. Fill in every section, then stage the entry with your change.

| Option            | Meaning                                                                     |
| ----------------- | --------------------------------------------------------------------------- |
| `--type`, `-t`    | One of the types below. Required.                                           |
| `--data-id`, `-d` | A registered Data ID. Repeat for more; the first one goes in the file name. |
| `--title`         | One plain-language line, under 120 characters. Required.                    |
| `--slug`          | Short file-name part. Defaults to the title.                                |
| `--breaking`      | Marks a breaking change (see rule 6).                                       |
| `--author`        | Overrides the git user name.                                                |

## Rules

1. **One entry per change** — per pull request. Review feedback on the same branch updates the same entry; it does not add a second one.
2. **File name** is `YYYY-MM-DD--type--DATA-ID--slug.md`. The date and type match the frontmatter; the Data ID is the first item in `dataIds`.
3. **Data IDs must already be registered** in [`src/lib/data-ids/registry.ts`](../src/lib/data-ids/registry.ts). Register first, then build (see [Docs/Data-IDs.md](../Docs/Data-IDs.md)).
4. **Plain language.** Write for the next developer, the backend developer and the client's project manager — not for yourself today.
5. **Entries are history.** Once merged to `main`, correct a wrong entry with a new entry. Fixing a typo is fine.
6. **`breaking: true`** when something other people rely on changes: an API contract, a design token name, a component prop, an environment variable, a route.

## Types

| `type`            | Use for                                            | Commit type            |
| ----------------- | -------------------------------------------------- | ---------------------- |
| `feature`         | A new capability someone can use                   | `feat`                 |
| `fix`             | A bug fix                                          | `fix`                  |
| `api-integration` | Moving a screen from mocks to a real endpoint      | `api`                  |
| `design`          | Tokens, visuals or motion, with no new capability  | `design`               |
| `refactor`        | Structure only — no behaviour change               | `refactor`             |
| `performance`     | Speed, bundle size, rendering cost                 | `perf`                 |
| `security`        | Hardening, dependency advisories, secrets handling | `security`             |
| `docs`            | Documentation only                                 | `docs`                 |
| `test`            | Tests only                                         | `test`                 |
| `chore`           | Tooling, dependencies, configuration, CI           | `chore`, `ci`, `build` |

## How it is enforced

| When                    | Command                                                                                             | Fails when                                                                |
| ----------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Every commit (hook)     | `npm run changelog:check -- --staged`, then `changelog:build` regenerates and stages `CHANGELOG.md` | An entry is invalid, or the commit changes files without staging an entry |
| Every pull request (CI) | `npm run changelog:check -- --base origin/<target>` and `npm run changelog:build -- --check`        | The branch has no entry, an entry is invalid, or `CHANGELOG.md` is stale  |

## Merge conflict in CHANGELOG.md

Entries never conflict — each is its own file. `CHANGELOG.md` can, because two branches regenerate it. Do not resolve it by hand:

```bash
npm run changelog:build
```

Then stage `CHANGELOG.md` and continue the merge.

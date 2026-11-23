# CI/CD

This document explains how this repository checks code automatically: what runs, when, why, and how to change it. It's written for the frontend developer, the backend developer, and AI agents working in this repository.

When you change a workflow, update this document in the same pull request.

## At a glance

| Workflow | Runs when | What it does |
| --- | --- | --- |
| [Pull request checks](../.github/workflows/pull-request.yml) | A pull request into `integration`, `staging` or `main` is opened, updated, reopened, or marked ready for review | Runs the checks for the apps the pull request changes |
| [After merge](../.github/workflows/after-merge.yml) | Commits reach `integration`, `staging` or `main` | Confirms they came through a merged pull request, runs the checks again, and keeps an alert issue open while the branch is failing |
| [Nightly](../.github/workflows/nightly.yml) | 02:00 IST when `integration` changed in the last day, or when started by hand | Runs every check on `integration`, plus a dependency audit |
| [Checks](../.github/workflows/checks.yml) | Only when one of the workflows above calls it | Defines every app's checks, in one place |
| [Dependabot](../.github/dependabot.yml) | Mondays at 09:00 IST | Opens dependency update pull requests into `integration` |

After merge and Nightly both use the [alert action](../.github/actions/alert/action.yml) to open and close alert issues. The [pull request template](../.github/pull_request_template.md) repeats the team rules at the moment you merge.

## How code moves

```text
feature branch ──▶ integration ──▶ staging ──▶ main
                   checks         reviewed    tested
```

- Work happens on feature branches, for example `frontend-foundation` or `backend-foundation`.
- A pull request merges a feature branch into `integration`. **The bar is the automated checks.**
- A pull request from `integration` into `staging`. **The bar is a review**, with whatever review tooling we are using.
- A pull request from `staging` into `main` releases it. **The bar is user and load testing** against what `staging` is running.
- Nobody pushes to `integration`, `staging` or `main` directly.

Three arrows, three different bars, and the checks run on all three. The checks are
the *floor*, not the whole gate: a green run into `staging` says nothing about
whether anyone reviewed it, and a green run into `main` says nothing about whether
it was load tested. Those are the parts a workflow cannot do for us.

## What our GitHub plan allows

The `polysil-crm` organization is on GitHub's free plan, and this repository is private. With that combination, GitHub runs checks but can't enforce them.

| Feature that needs a paid plan | What we do instead |
| --- | --- |
| Required status checks and [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Merge only when **CI passed** is green. After merge flags anything that slips through. |
| [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) that block direct pushes | After merge fails and opens an alert issue when a commit arrives without a merged pull request. |
| [Merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Update a branch from its target before merging, so the checks ran on what you merge. |
| Required reviewers before a [deployment](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | Once deploys exist, start production deploys by hand. |

GitHub Actions is included on the free plan, with a monthly allowance of minutes. For details, see [Stay within the free minutes](#stay-within-the-free-minutes).

If the organization moves to a paid plan later, add a ruleset for `integration`, `staging` and `main` with these rules:
- Require a pull request.
- Require the **CI passed** check.
- Require one approval.
- Block force pushes and deletions.

The workflows need no changes.

## The checks

All checks live in [checks.yml](../.github/workflows/checks.yml). The other workflows only decide when to run it, and how much of it.

### Which apps a run checks

The first job, **Find the apps to check**, compares the change with its base:
- On a pull request, the base is the target branch.
- After a merge, the base is the previous commit on the branch.

| Files changed under | Checks that run |
| --- | --- |
| `Frontend/` | Frontend |
| `backend/` | Backend |
| `.github/` | Both, because a workflow change can break either one |

An app is checked only if its folder exists on that commit. Nightly runs check every app. Each run's summary page shows which apps it checked.

### Frontend (`Frontend/`)

The frontend developer owns these checks. Every command runs inside `Frontend/`.

| Job | Runs | Commands |
| --- | --- | --- |
| Frontend: checks and build | Whenever the frontend is checked | `npm ci`, `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`, `npm run knip`, the changelog checks, `npm run build` |
| Frontend: Storybook accessibility | Pull requests that aren't drafts, after merge, and nightly | `npm run test:storybook` |
| Frontend: Playwright smoke tests | Same as Storybook | `npm run test:e2e`, which builds and starts the app with the mocked API |

Notes:
- **Builds:** they use `NEXT_PUBLIC_APP_ENV=feature`, so the API is mocked and no secrets are needed.
- **Changelog:** a pull request that changes the frontend needs an entry in `Frontend/changelog/entries/`; see `Frontend/changelog/README.md`. Dependabot pull requests are exempt, so if an update changes behaviour, add an entry by hand.
- **Running locally:** `npm run verify` runs the fast checks on your machine.
- **`Frontend/.github/`:** holds the CI and pull request template from when the frontend was a standalone repository. GitHub only reads the root `.github/`, so those files have no effect here.
- **Git hooks:** the frontend's hooks in `Frontend/.husky/` don't install here, because `Frontend/` isn't the repository root.

### Backend (`backend/`)

The backend developer owns these checks. Every command runs inside `backend/`.

| Job | Runs | Commands |
| --- | --- | --- |
| Backend: lint and types | Whenever the backend is checked | `ruff check .`, then `mypy --strict api/domain api/services` |
| Backend: tests | Whenever the backend is checked | roles, `alembic upgrade head`, the demo seed, the reference SQL, then `pytest` |

`mypy` runs on `api/domain` and `api/services` and nothing else, because that is
what `backend/CLAUDE.md` puts it on. The rest of the tree is not strict-clean, and
a tick that covers less than it appears to is worse than an honest narrower one.

#### The three containers, and why PgBouncer is not optional

The tests job runs Postgres 16, PgBouncer and Redis as service containers, which
is the same shape as the local stack.

**PgBouncer in transaction mode is the point, not plumbing.** Every request sets
the caller's identity with `set_config(..., true)` so it dies with the
transaction. Written as a plain `SET` instead, the identity leaks to whoever
borrows that pooled connection next — and that passes every test in the suite
except one, which can only fail against a real transaction-mode pooler. Running
CI against a direct connection would go green and prove nothing about the thing
most worth proving.

So: Postgres is reached **only** through PgBouncer on 6432. The single exception
is creating the two cluster roles, which is not application traffic.

#### What the job does, in order

1. **Creates `app_role` and `app_anon`** directly on Postgres. Roles are cluster
   objects and a migration is per-database, so `CREATE ROLE` in a migration would
   fail on the second database in the same cluster. It is an out-of-band step
   everywhere, including here.
2. **Writes `infra/.env`** with the three values `scripts/seed_demo.py` reads from
   there and nowhere else.
3. **`alembic upgrade head`.** The `DATABASE_URL` names the asyncpg driver; Alembic
   rewrites it to psycopg itself, so one variable serves both.
4. **Seeds** the roles, the permission matrix parsed from `RBAC.md`, and the
   administrator. The parity suite builds its own permission rows, but the API
   tests sign in as a seeded user.
5. **Checks the reference SQL** still describes the database it just built.
6. **Runs `pytest`.**

#### What CI cannot run, and why that is on purpose

Some tests skip, and the run prints each one with its reason (`-rs`).

The client's workbooks — the three sample subsidy quotations and the product
master — are **deliberately not in this repository**. They carry the client's own
component rates and prices. So anything that feeds on them skips:

| Skipped | Needs |
| --- | --- |
| The three golden subsidy quotations | `tests/fixtures/subsidy/{drip,mini_sprinkler,sprinkler}.json` |
| The subsidy endpoint tests | the same, plus masters loaded by `scripts/load_subsidy_masters.py` |
| Two price-list tests that need a catalogue | products loaded by `scripts/load_product_master.py` |

Everything else runs: the interpolation and its boundaries against the published
scheme tables, the whole commercial tax engine, every migration's constraints, the
RLS policies including the negative cases, the permission parity suite, and every
endpoint that does not need the client's own figures.

**This is a real gap and worth naming rather than hiding.** The golden tests are
what prove the subsidy engine reproduces the client's spreadsheets to the paisa,
and CI does not run them. They run on a developer's machine, where the workbooks
are, and the mutation checks (`scripts/mutation_check_subsidy.py`,
`scripts/mutation_check_pricing.py`) run there too.

### CI passed

**CI passed** sums up a run in a single check:
- It fails when any check failed or was cancelled.
- It passes when every check that ran passed. A skipped check counts as passed, because it had nothing to check.

Watch this one check rather than each job. It also keeps the setup ready for a paid plan:
- When path filters stop a whole workflow from starting, GitHub leaves its required checks pending forever.
- A job skipped by a condition counts as passed ([GitHub docs](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)).

So these workflows always start, skip individual jobs instead, and **CI passed** always reports.

## After merge

[after-merge.yml](../.github/workflows/after-merge.yml) runs for every push to `integration` or `main`:

1. **Arrived through a pull request** asks GitHub for the merged pull request linked to the commit ([commits API](https://docs.github.com/en/rest/commits/commits)). GitHub can take a moment to link them, so the job retries for about a minute. A commit without a merged pull request into that branch fails this job.
2. **Checks** runs the same checks as a pull request, compared with the previous commit on the branch.
3. **Alert while the branch is failing** keeps one open issue per branch, titled `CI: integration is failing` or `CI: main is failing`:
   - The first failure opens the issue.
   - Later failures add a comment.
   - The next passing commit closes it.

   To get these notifications, watch the repository on GitHub.

When an alert opens, open the run linked in the issue, and fix forward with a pull request. Don't push a revert straight to the branch.

### Deploys

No deploy runs from CI yet. When one does, add deploy jobs to `after-merge.yml`
with `needs: checks`, so a failing commit never deploys:

- `staging` deploys to the staging box.
- `main` deploys to production, started by hand, because this plan has no deployment approvals.

**The backend already has a deploy, and it is not wired to CI.**
`backend/scripts/deploy_staging.py` puts the API on the shared box that serves
`https://polysil-api.pranayx.tech`, and it is run from a developer's machine
because it needs an SSH key. Moving it here means putting that key in Actions
secrets, which is a decision rather than a task: the box hosts two unrelated
projects.

One thing that deploy learned, for whoever writes the job: **check the URL a user
would use, not the one the deploy can reach.** Its health step asked the box over
loopback, which stayed green while the public address answered 502 for everyone,
because a container had come back without the reverse proxy's network. A check
that does not take the same hops as a real request can be green during an outage
(`backend/docs/issues/OPEN.md`, ISS-091).

## Nightly

[nightly.yml](../.github/workflows/nightly.yml) watches `integration` for problems that don't arrive through a code change:

- **When it starts working:** GitHub runs scheduled workflows from the default branch only ([GitHub docs](https://docs.github.com/actions/using-workflows/events-that-trigger-workflows)), so this workflow starts once it reaches `main`. It checks out `integration` explicitly.
- **Quiet nights:** it skips a night when `integration` hasn't changed in the last 25 hours. To force a run, use **Run workflow** in the Actions tab.
- **What it runs:** every check for every app, plus `npm audit --omit=dev --audit-level=high` for the frontend.
- **Alerts:** a failure keeps the issue `CI: nightly checks are failing on integration` open until a later night passes.

## Dependabot

[dependabot.yml](../.github/dependabot.yml) proposes updates every Monday at 09:00 IST. It covers `Frontend/` (npm), `backend/` (pip, read from `pyproject.toml` ([PEP 621 support](https://github.blog/changelog/2022-10-24-dependabot-updates-support-for-the-python-pep-621-standard/))), and the GitHub Actions the workflows use.

- **Where updates go:** version updates open against `integration`. Minor and patch updates are grouped into one pull request per app.
- **Waiting period:** npm and pip updates wait 7 days after a release ([cooldown](https://github.blog/changelog/2025-07-01-dependabot-supports-configuration-of-a-minimum-package-age/)). That gives the community time to catch a compromised release.
- **Security updates:** they always open against `main`, whatever `target-branch` says ([Dependabot options](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)). Change their base branch to `integration` before merging.
- **When it starts:** Dependabot reads this file from `main`, so updates start once it reaches `main`.

## Stay within the free minutes

The organization's private repositories share 2,000 GitHub Actions minutes a month. Beyond that, Linux runners cost $0.006 a minute ([Actions billing](https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions), [2026 prices](https://github.blog/changelog/2025-12-16-coming-soon-simpler-pricing-and-a-better-experience-for-github-actions/)).

Estimated cost of one run, based on local timings:
- Frontend fast checks: about 6 minutes.
- Frontend, including Storybook and Playwright: about 15 minutes.
- Backend lint and types: about 3 minutes.
- Backend tests: **not measured yet.** It takes about 35 minutes on a developer's
  machine, but almost all of that is network latency to a remote database roughly
  150 ms per round trip away. In CI the database is a container on the same host,
  so expect far less. Replace this line with the real figure after the first run.

To stay inside the allowance:
- Open pull requests as drafts while you're still pushing. Mark them ready when you want the slower suites. **That gate now covers the backend tests too**, so a draft gets lint and types only.
- Don't worry about pushing again: a new push to a pull request cancels the run for the previous push.
- Check usage in the organization's billing settings.

## Change the setup

- **Add a check to an app:** add a step to that app's job in `checks.yml`, then update this document.
- **Add an app:**
  1. In **Find the apps to check**, add a folder check and a path pattern.
  2. Add a job with `needs: changes` and `if: needs.changes.outputs.<app> == 'true'`.
  3. Add the job to the `needs` list of **CI passed**.
  4. Document it here.
- **Change when something runs:** edit the workflow that calls `checks.yml` (`pull-request.yml`, `after-merge.yml` or `nightly.yml`), not `checks.yml` itself.
- **Rename a job carefully:** a future ruleset requires checks by name, especially **CI passed**.
- **Test a workflow change:** open a pull request into `integration`. A pull request runs the workflow files from its own branch.

## Troubleshooting

| What you see | Likely cause |
| --- | --- |
| No checks on a pull request | It doesn't target `integration` or `main`. If you changed its base branch after opening it, push a commit or re-run the checks. |
| Frontend or backend checks were skipped | Nothing changed under that app's folder or `.github/`, or the app's folder doesn't exist on the target branch yet. |
| "This pull request has a changelog entry" failed | The pull request changes `Frontend/` without an entry. Run `npm run changelog:new` inside `Frontend/`. |
| An alert issue opened | Open the run linked in the issue. The issue closes itself when a later commit passes. |
| "Arrived through a pull request" failed, but you used one | GitHub linked the commit late. Re-run the job. If it fails again, check that the pull request targeted this branch. |
| Nightly never runs | `nightly.yml` isn't on `main` yet. |
| No Dependabot pull requests | `dependabot.yml` isn't on `main` yet, or the app's folder isn't on `integration` yet. |

## History

- 15 September 2026: first version, with pull request checks, the after-merge guard, the nightly run, and Dependabot.

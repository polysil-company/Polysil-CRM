# CI/CD

This document explains how this repository checks code automatically: what runs, when, why, and how to change it. It's written for the frontend developer, the backend developer, and AI agents working in this repository.

When you change a workflow, update this document in the same pull request.

## At a glance

| Workflow | Runs when | What it does |
| --- | --- | --- |
| [Pull request checks](../.github/workflows/pull-request.yml) | A pull request into `integration` or `main` is opened, updated, reopened, or marked ready for review | Runs the checks for the apps the pull request changes |
| [After merge](../.github/workflows/after-merge.yml) | Commits reach `integration` or `main` | Confirms they came through a merged pull request, runs the checks again, and keeps an alert issue open while the branch is failing |
| [Nightly](../.github/workflows/nightly.yml) | 02:00 IST when `integration` changed in the last day, or when started by hand | Runs every check on `integration`, plus a dependency audit |
| [Checks](../.github/workflows/checks.yml) | Only when one of the workflows above calls it | Defines every app's checks, in one place |
| [Dependabot](../.github/dependabot.yml) | Mondays at 09:00 IST | Opens dependency update pull requests into `integration` |

After merge and Nightly both use the [alert action](../.github/actions/alert/action.yml) to open and close alert issues. The [pull request template](../.github/pull_request_template.md) repeats the team rules at the moment you merge.

## How code moves

```text
feature branch ── pull request ──▶ integration (staging) ── pull request ──▶ main (production)
```

- Work happens on feature branches, for example `frontend-foundation` or `backend-foundation`.
- A pull request merges a feature branch into `integration`.
- A pull request from `integration` into `main` releases it.
- Nobody pushes to `integration` or `main` directly.

## What our GitHub plan allows

The `polysil-crm` organization is on GitHub's free plan, and this repository is private. With that combination, GitHub runs checks but can't enforce them.

| Feature that needs a paid plan | What we do instead |
| --- | --- |
| Required status checks and [rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets) | Merge only when **CI passed** is green. After merge flags anything that slips through. |
| [Protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches) that block direct pushes | After merge fails and opens an alert issue when a commit arrives without a merged pull request. |
| [Merge queue](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Update a branch from its target before merging, so the checks ran on what you merge. |
| Required reviewers before a [deployment](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | Once deploys exist, start production deploys by hand. |

GitHub Actions is included on the free plan, with a monthly allowance of minutes. For details, see [Stay within the free minutes](#stay-within-the-free-minutes).

If the organization moves to a paid plan later, add a ruleset for `integration` and `main` with these rules:
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
| Backend: lint | Whenever the backend is checked | `pip install -e ".[dev]"`, `ruff check .` |

The backend test suite doesn't run in CI yet. According to `backend/README.md` and `backend/infra/`, it needs:

- Postgres 16, reached only through PgBouncer in transaction mode on port 6432. The backend refuses direct connections on purpose.
- The `app_role` role, and `app_anon` where it's used, created by a cluster admin.
- Migrations applied with Alembic.
- `DATABASE_URL` (asyncpg driver, port 6432) and `JWT_SECRET`.
- Redis, for the worker.

To add the suite to CI:
1. Give the backend job service containers for Postgres, PgBouncer and Redis.
2. Add steps that create the roles and run the migrations.
3. Run `pytest`. Consider running `mypy` in the same job, with the arguments you use locally.
4. Delete the job's "not wired in yet" notice step.

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

There are no deploys yet, because hosting isn't chosen. When it is, add deploy jobs to `after-merge.yml` with `needs: checks`, so a failing commit never deploys:
- Staging deploys from `integration`.
- Production deploys from `main`, started by hand, because this plan has no deployment approvals.

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
- Backend lint: about 2 minutes.

To stay inside the allowance:
- Open pull requests as drafts while you're still pushing. Mark them ready when you want the slower suites.
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

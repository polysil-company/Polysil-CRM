# Polysil CRM — web frontend

The CRM and dealer management web app for **Polysil Irrigation** (Vadodara, Gujarat), built by **Loopify Solutions**. This repository is the frontend; the API is built separately by the backend developer.

> **Status, 15 September 2026:** the frontend foundation and sign-in are in place. Staff sign in with email and password, channel partners with a one-time code; navigation follows each user's permissions. Everything runs against a mocked API built from the backend's contract; integration on staging comes next.

## Start here

| Read                                                                                            | For                                                         |
| ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [AGENTS.md](AGENTS.md)                                                                          | **Mandatory.** The rules for every contributor, human or AI |
| [src/styles/tokens.css](src/styles/tokens.css) · [Docs/Design-System.md](Docs/Design-System.md) | The design system: the tokens and how to use them           |
| [Docs/Frontend-Architecture.md](Docs/Frontend-Architecture.md)                                  | Stack, folders, data layer, forms and testing               |
| [Docs/Frontend-Scope.md](Docs/Frontend-Scope.md)                                                | What we are building, the roles and the open questions      |
| [Docs/Data-IDs.md](Docs/Data-IDs.md)                                                            | Functionality IDs shared with the backend                   |
| [Docs/Logging.md](Docs/Logging.md)                                                              | The log format and the runtime log level                    |
| [Docs/Environments.md](Docs/Environments.md)                                                    | Feature → Staging → Production                              |
| [changelog/README.md](changelog/README.md) · [CHANGELOG.md](CHANGELOG.md)                       | How every change is recorded                                |

## Run it

You need Node.js 24.13 or newer (see `.nvmrc`) and npm 11.

```bash
npm ci
```

```bash
cp .env.example .env.local
```

```bash
npm run dev
```

Open http://localhost:3000. In development the API is mocked with MSW, so no backend is needed. Sign in as staff with any email and the password `polysil-demo`, or as a channel partner with any Indian mobile number and the code `123456`. The user menu (top right) lets you preview the app as another role and switch the data scenario — slow, empty, error or a broken contract — to see every state.

To preview and tweak components in isolation:

```bash
npm run storybook
```

## Commands

| Command                  | What it does                                                               |
| ------------------------ | -------------------------------------------------------------------------- |
| `npm run dev`            | The app on http://localhost:3000 with the mocked API                       |
| `npm run storybook`      | Components in isolation on http://localhost:6006                           |
| `npm run verify`         | Type check, lint, unit tests and changelog check — run before pushing      |
| `npm test`               | Unit and component tests                                                   |
| `npm run test:storybook` | Every story in Chromium, with accessibility checks                         |
| `npm run test:e2e`       | Playwright smoke tests                                                     |
| `npm run changelog:new`  | Creates a changelog entry — see [changelog/README.md](changelog/README.md) |
| `npm run build`          | Production build                                                           |

The browser-based test suites need `npx playwright install chromium` once per machine. The full list of commands is in [AGENTS.md](AGENTS.md) §12.

## Conventions

- **Branches:** `feature/LEAD-002-new-lead-dialog` → `staging` → `main`.
- **Commits:** `feat(LEAD-002): add the new lead dialog` — the scope is a Data ID.
- **Every change** ships with a changelog entry and tests. Run `npm run verify` before pushing.
- **Secrets** live with the hosting provider only — never in the repository or `Docs/`.

## Background documents

Planning documents from the earlier, wider scope: [Requirements](Docs/Requirements.md), [Plan](Docs/Plan.md), [Architecture](Docs/Architecture.md), [Decisions](Docs/Decisions.md), [Open questions](Docs/Open-Questions.md), [Issues](Docs/Issues.md), [Testing](Docs/Testing.md) and [Acceptance criteria](Docs/Acceptance-Criteria.md). Where they disagree with the frontend documents above, the frontend documents win — [Docs/Frontend-Scope.md](Docs/Frontend-Scope.md) §1 explains what changed. The previous contributor rules are archived in [Docs/archive/pre-pivot](Docs/archive/pre-pivot/AGENTS.pre-pivot.md).

_Private repository. Client-confidential._

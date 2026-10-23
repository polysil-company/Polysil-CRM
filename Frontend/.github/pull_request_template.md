## What changed

<!-- One or two sentences in plain language. Link the changelog entry. -->

## Data IDs

<!-- e.g. LEAD-002. Every ID is registered in src/lib/data-ids/registry.ts before the work starts. -->

## Checklist

- [ ] Changelog entry added or updated in `changelog/entries/` — Before, Now, Discussion, Files changed, Tests
- [ ] Tests added or updated; each top-level `describe` starts with its Data ID
- [ ] Every API call handles loading, empty, error (with reference), stale data, cancellation and contract violations
- [ ] Logger used in every new handler and API call (File → Function → Request → Response); no personal data logged
- [ ] Responsive at 360px, 768px and 1280px, in light and dark
- [ ] Keyboard and screen reader: visible focus, names on icon-only buttons, no new accessibility violations
- [ ] Design tokens only — no arbitrary colours, sizes, radii, layers or durations
- [ ] Stories added or updated for new or changed components
- [ ] `npm run verify` passes locally

## Screenshots or recording

<!-- For UI changes: phone and desktop, light and dark. -->

## Environments

- [ ] Checked on the feature branch preview (mocked API)
- [ ] Checked on staging against the real backend (API integrations only)

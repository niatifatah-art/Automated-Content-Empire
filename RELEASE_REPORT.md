# ACE v2.0.1 release verification

Date: 2026-07-29

## Why this patch exists

ACE v2.0.0 exposed four real upgrade/runtime defects on an existing installation:

1. Legacy accounts were loaded without the new required `editing` block.
2. A Gemini 3.6 Flash `429` placed the whole credential in cooldown, so ACE could not try another Gemini model with the same authorized key.
3. Existing configuration routes were preserved during `ace init --upgrade`, which left Gemini 3.6 followed directly by degraded local models.
4. Empty caption/visual/edit inspections were reported as `passed` after an early pipeline failure.

## Corrections

- Added persistent account migration and an in-memory compatibility merge.
- Added model-scoped provider cooldowns.
- Added this cloud ladder before local degraded routes:
  - Gemini 3.6 Flash
  - Gemini 3.5 Flash
  - Gemini 3.5 Flash-Lite
  - enabled OpenAI route, when configured
  - explicit degraded local routes
- Added primary-then-backup credential ordering for each preferred model.
- Added route enrichment during `ace init --upgrade`, while retaining custom local models.
- Removed deprecated sampling parameters from Gemini 3.5/3.6 requests.
- Increased credential-test output allowance for thinking-enabled models.
- Corrected empty diagnostics to `not_run`.
- Corrected interrupted-generation research counts.
- Fixed `--free-only` so it does not accidentally force an invalid single-provider `auto` model route.

## Verification

| Check | Result |
|---|---|
| Python compilation | PASS |
| Unit/regression suite | 19/19 PASS |
| Model-scoped 429 fallback test | PASS |
| Backup credential before lower-model test | PASS |
| Legacy account migration | PASS |
| Legacy route enrichment | PASS |
| Source full self-test | PASS |
| 1080×1920 FFmpeg render | PASS |
| Caption overflow validation | PASS |
| Visual-plan validation | PASS |
| Warning completion logic | PASS |
| Wheel build | PASS |
| Installed-wheel self-test | PASS |

## Live-service boundary

No private API keys were available in the release sandbox, so the release process did not make a live Gemini, Pexels, Pixabay, OpenAI, GIPHY, or Tenor request. The exact Gemini failure path was reproduced through deterministic provider tests using a `429 rate_limit` failure followed by successful cloud-model or backup-credential failover.

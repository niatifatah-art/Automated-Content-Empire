# ACE v2.1.0 release verification

Date: 2026-07-30

## Release objective

ACE v2.1.0 turns the v2.0.2 Visual Intelligence foundation into a more practical Creative Editing Engine. The release focuses on truthful B-roll direction, distinct visual languages, restrained meme timing, shot-specific motion and sound cues, reference pacing, an honest creative quality gate, and a simpler creator-facing command set.

## Main changes

- Added the five-command workflow: `ace make`, `ace review`, `ace redo`, `ace open`, and `ace checkup`.
- Added friendly controls: `--look`, `--footage`, `--humor`, `--mode`, and `--ref`, while preserving old aliases.
- Added diverse B-roll searches for action, object detail, over-the-shoulder context, environment, interaction and documentary coverage.
- Separated actual stock/account B-roll coverage from browser/demo/explainer coverage in quality reports.
- Added a natural Meme Director with serious-topic suppression and a maximum two-meme video budget.
- Added distinct browser DNS, routed DNS, HTTPS, request/response, network, terminal, application and code-flow visual languages.
- Added stricter secondary-visual selection: relevant live cutaways or UI/evidence PIP only.
- Added motion, transition, emphasis, source-window and SFX directives per shot.
- Added scene-aware B-roll trimming, hard-cut-first editing, restrained fades, vertical subject preservation and generated license-free SFX.
- Added reference-video cut-rhythm analysis.
- Added quality-mode cloud budgets and daily Gemini quota classification.
- Added a creative quality gate for real B-roll, dynamic coverage, static cards, repeated concepts, motion/transition variety, meme density and pace.
- Added browser/DNS and public-Wi-Fi real-render regression fixtures.

## Verification results

| Check | Result |
|---|---|
| Python compilation | PASS |
| Unit/regression suite | 50/50 PASS |
| Intent-planning benchmark | 10/10 PASS, 100.0 average |
| Source full self-test | PASS |
| Wheel build | PASS |
| Fresh wheel CLI | `ACE 2.1.0` |
| Fresh wheel visual benchmark | PASS |
| Fresh wheel quick self-test | PASS |
| Browser creative regression | PASS |
| Browser regression creative score | 100/100 |
| Browser regression visual relevance | 91.33/100 |
| Browser regression overall visual score | 95.12/100 |
| Browser regression meme count | 0 |
| Browser regression black/silence ratio | 0.0 / 0.0 |
| Public-Wi-Fi visual relevance | 93.94/100 |
| Public-Wi-Fi overall visual score | 96.11/100 |
| Embedded-secret scan | PASS |

## Important interpretation

The ten-case benchmark measures deterministic intent planning, not subjective finished-video excellence. Release verification therefore also renders real MP4 files and reviews a frame contact sheet.

The browser regression intentionally uses no stock provider and no cloud credential. It verifies original browser, DNS, encryption and request/response visual languages. Real Pexels/Pixabay B-roll inventory and live Gemini frame judging require the user's private credentials and network access, so those provider calls were not executed inside the release sandbox.

## Remaining boundaries

- ACE is not a full nonlinear editor and does not claim human-level motion tracking or guaranteed audience retention.
- B-roll quality depends on provider inventory and the actual sampled frames; `best` mode stops at the creative gate when the result remains weak.
- Internet meme and GIF reuse remains approval-gated.
- Direct social publishing remains disabled.

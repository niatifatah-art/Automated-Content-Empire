# ACE v2.0.2 release verification

Date: 2026-07-30

## Release objective

ACE v2.0.2 replaces broad stock-first matching with a Visual Intelligence pipeline that decides the clearest visual language for each narrated idea. Pexels and Pixabay remain available, but official evidence, controlled demonstrations, original explainers, charts, account assets, generated concepts, typography, and minimal screens can rank above stock when they communicate the idea more accurately.

## Implemented systems

- Strict `ShotIntent`, `VisualCandidate`, `VisualScore`, `VisualDecision`, and `VisualValidationReport` contracts.
- Deterministic Visual Intent Planner with optional Gemini refinement.
- Candidate-format routing and quality tournament.
- Original animated explainers and controlled demonstrations for networking, encryption, rogue hotspots, VPNs, passkeys, browser HTTPS, terminal commands, phone hotspots, code logic, software routing, partnerships, timelines, challenges, and comparisons.
- Deterministic semantic scoring with forbidden-element rejection and optional cloud frame judging.
- Sentence/idea-level shot grouping instead of changing visuals for every caption phrase.
- Caption adaptation after visual selection to avoid covering diagrams, evidence, UI, and terminal demonstrations.
- Per-shot candidate records, explanations, replacement history, approvals, and repair commands.
- Exact and perceptual image/video fingerprints.
- SQLite generation stage/event/approval state.
- Structured provider attempt tracing.
- Ten-case visual benchmark and public-Wi-Fi regression test.
- GitHub Actions CI, repository secret scan, packaging verification, sanitized `.env.example`, and contribution guidance.

## Verification results

| Check | Result |
|---|---|
| Python compilation | PASS |
| Unit/regression suite | 33/33 PASS |
| Visual benchmark | 10/10 PASS, 100.0 average |
| Source full self-test | PASS |
| Installed-wheel full self-test | PASS |
| Wheel build | PASS |
| Fresh installed-wheel CLI | `ACE 2.0.2` |
| Public-Wi-Fi regression render | PASS |
| Regression output | H.264 + AAC, 1080×1920, 30 fps |
| Regression duration | 27.63 seconds |
| Caption overflow | 0 |
| Missing visuals | 0 |
| Black-frame ratio | 0.0 |
| Silence ratio | 0.0 |
| Generic filler ratio | 0.0 |
| Unexplained visual decisions | 0 |
| Exact/perceptual duplicate decisions | 0 |
| Public-Wi-Fi average relevance | 93.42/100 |
| Public-Wi-Fi average overall visual score | 95.92/100 |
| Final completion state | COMPLETE |
| Embedded-secret scan | PASS |

## Public-Wi-Fi regression

The regression reused a fixed script and narration while rebuilding only the visual route. The final seven-shot render intentionally uses:

- shared router/devices and exposed packet animation;
- encrypted packet animation;
- trusted versus lookalike rogue hotspot demonstration;
- VPN tunnel explainer;
- literal Personal Hotspot settings demonstration;
- intentional final typography.

It contains no fire metaphor, financial chart, generic office interview, generic hacker footage, missing visual, or black fallback.

## Live-service boundary

No private API credentials were available in the release sandbox. Live Gemini refinement/frame judging, Pexels, Pixabay, Openverse, Wikimedia, browser capture, cloud-image, GIPHY, and Tenor requests were therefore not executed. The deterministic Visual Intelligence pipeline, provider routing/tracing logic, candidate scoring, original explainers, full FFmpeg render, packaging, installed-wheel behavior, and repair/state commands were tested locally.

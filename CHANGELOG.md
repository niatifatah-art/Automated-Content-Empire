# Changelog

## 2.1.0 — 2026-07-30

### Creative Editing Engine

- Added simplified `ace make`, `review`, `improve`, `play`, and `doctor` commands while retaining the advanced command set.
- Added diverse B-roll query planning for literal action, object detail, over-the-shoulder context, environment and documentary coverage.
- Connected original meme candidates to Autopilot with serious-topic suppression and a style-specific humor budget.
- Added per-shot edit directives for motion, transition, overlay, emphasis, B-roll start windows and optional SFX intent.
- Added scene-boundary-aware B-roll trimming and optional secondary visual overlays.
- Removed repeated fade-to-black dips between every shot.
- Added reference-video pacing analysis through `ace make --reference`.
- Added creative quality inspection for B-roll coverage, static-card ratio, repeated formats, motion variety, transition variety and meme density.
- Added daily Gemini quota classification and reset-length route cooldowns with concise errors.
- Increased ACE-native candidate diversity and stock-query diversity per shot.

## 2.0.2 — 2026-07-30

### Visual Intelligence

- Added strict `ShotIntent`, `VisualCandidate`, `VisualScore`, `VisualDecision`, and validation contracts.
- Added a deterministic Visual Intent Planner with optional cloud refinement.
- Added a candidate-format router and tournament across evidence, demonstrations, original explainers, account assets, stock, typography, charts, timelines, and minimal screens.
- Added original animated explainers and controlled demonstrations for shared networks, encryption, rogue hotspots, VPNs, passkeys, browser HTTPS, terminal commands, phone hotspots, code logic, software routing, partnerships, timelines, challenges, and comparisons.
- Grouped caption phrases into sentence/idea-level shots so visual changes follow meaning rather than every subtitle chunk.
- Added post-selection caption adaptation so evidence, demonstrations, and explainers keep their important regions readable.
- Added deterministic relevance scoring plus an optional Gemini frame judge.
- Added per-shot candidate artifacts, explanations, approvals, replacement history, and strict relevance/filler thresholds.
- Added the ten-case visual benchmark and public-Wi-Fi regression rules.

### Reliability and workflow

- Added a SQLite stage/event/approval database for every generation.
- Added provider attempt traces with generation, stage, shot, model, credential, timing, failure category, and usage metadata.
- Added exact and perceptual image/video fingerprints for duplicate detection and visual provenance.
- Added `ace visuals explain`, `candidates`, `regenerate`, `replace`, `approve`, and `benchmark`.
- Added `ace rerun --from visual-plan|captions|editing|render` and `ace state show|events`.
- Added GitHub Actions CI, package verification, a repository secret scan, sanitized `.env.example`, and contribution guidance.
- Updated offline self-tests to exercise the real Visual Intelligence route.

## 2.0.1 — 2026-07-29

- Added model-aware Gemini quota failover across primary/backup credentials and 3.6 Flash, 3.5 Flash, and 3.5 Flash-Lite.
- Added safe account migration for the required editing profile.
- Fixed false-passing empty caption/visual/edit diagnostics.
- Fixed Gemini credential smoke tests for thinking-enabled models and removed deprecated 3.x sampling parameters.
- Fixed research counts in interrupted-generation status reports.

## 2.0.0 — 2026-07-29

### Cloud and resilience

- Added cloud-first routing for research, writing, review, fact checking, quality, and visual planning.
- Added primary and backup Gemini credential slots with cooldown, failure classification, and state tracking.
- Disabled silent local-model substitution for quality-sensitive work.
- Added explicit `--allow-degraded` local emergency mode.
- Added credential and quota status commands.

### Research and evidence

- Added source discovery, URL ingestion, social-post ingestion, credibility scoring, claim extraction, claim-to-source mapping, and contradiction records.
- Added ACE-rendered article and social evidence cards.
- Added optional Playwright capture for official pages and approval-gated nonofficial captures.
- Separated research references, evidence, reusable media, and generated illustrations.

### Visuals and resources

- Added semantic shot planning and per-shot search queries.
- Added account assets, Pexels, Pixabay, Openverse, Wikimedia, generated graphics, and cloud image routes.
- Added vertical subject preservation with a blurred background for landscape media.
- Added deterministic clip offsets, short transitions, and original nonblack fallback visuals.
- Added meme catalog, tone-fit checks, generated meme cards, and approval metadata for internet candidates.

### Captions and editing

- Replaced sentence-sized subtitles with an adaptive Caption Director.
- Added no-caption, phrase, keyword, title, evidence, social, code, statistic, challenge, and CTA modes.
- Added safe-area fitting, dynamic font sizing, two-line limits, ASS output, accessibility SRT, and overflow validation.
- Added editing styles for technical, documentary, gaming, challenge, serious, and playful content.
- Added narration normalization, compression, music ducking hooks, black-frame detection, silence detection, and editing inspection.

### Reliability

- Fixed high-scoring warning reports being incorrectly marked `INCOMPLETE`.
- Added complete generation status and repair flows.
- Added unit tests and a full offline 1080×1920 FFmpeg release smoke test.
- Added approval-gated publishing-plan scaffolding.

# ADR 0022 — Creative Editing Engine

Status: Accepted for ACE v2.1.0.

## Problem

A technically valid video can still feel like a slideshow. ACE v2.0.2 could produce truthful shot-specific diagrams, but it lacked enough real B-roll direction, visual-language diversity, restrained meme timing, motion grammar, sound cues and simple creator-facing controls.

## Decision

ACE v2.1 adds a creative layer without replacing the evidence and provenance foundation:

1. Group captions into spoken ideas so one sentence does not generate several nearly identical templates.
2. Generate multiple literal B-roll searches for action, object detail, over-the-shoulder context and environment.
3. Keep real B-roll separate from browser demos and animated explainers in quality reports.
4. Compare at least two distinct ACE-native visual languages when the concept supports them.
5. Use original memes only for a genuine comedy beat and enforce a per-video style budget.
6. Attach a motion, transition, emphasis, SFX and source-window directive to every shot.
7. Use hard cuts as the normal transition; reserve brief fades and effects for deliberate moments.
8. Allow only semantically strong live cutaways or UI/evidence PIP overlays.
9. Analyze a user-supplied reference video for orientation and cut rhythm without copying its content.
10. Stop `best` mode at the creative quality gate rather than publishing a weak slideshow silently.
11. Expose a five-command workflow: `make`, `review`, `redo`, `open`, and `checkup`.

## Engineering choice

The renderer remains FFmpeg-based. FFmpeg already provides the scaling, overlay, zoom/pan, audio mixing, side-chain compression and transition primitives ACE needs, avoids a second JavaScript rendering stack, and keeps Linux installation predictable. Remotion remains a useful future plugin target for complex React-authored motion graphics, but is not embedded in the core release.

## Quality model

ACE reports independent measures for:

- actual stock/account B-roll coverage
- dynamic demo/explainer coverage
- static-card ratio
- repeated-format runs
- motion and transition diversity
- meme budget
- average shot duration

A passing deterministic intent benchmark does not prove finished-video quality. Release verification therefore includes a real FFmpeg render and a visual contact-sheet review.

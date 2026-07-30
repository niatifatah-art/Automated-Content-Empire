# ACE v2 architecture

## Pipeline

```text
Account identity
  ↓
Research discovery and source ingestion
  ↓
Candidate scripts → scoring → review
  ↓
Claim extraction → source mapping → contradiction checks
  ↓
Evidence cards and approved official-page captures
  ↓
TTS-safe script → account voice → normalized narration
  ↓
Adaptive Caption Director
  ↓
Semantic Visual Director
  ↓
Stock/account/evidence/generated/meme resource routing
  ↓
FFmpeg edit, audio mix, caption burn
  ↓
Media, caption, visual, factual, and completion validation
  ↓
Human-approved publishing plan
```

## Separation of concerns

ACE uses distinct stores because a resource may be useful in one role and unsafe in another:

- `research/`: information used to understand or verify claims.
- `evidence/`: visual representations of sources, headlines, or posts.
- `resources/publishable/`: reusable stock or account-owned media.
- `resources/reference-only/`: material that may guide research but must not be rendered.
- `visuals/generated/`: original diagrams, cards, memes, and fallback visuals.
- `licenses/`: source, attribution, origin, and approval metadata.

An article image is never assumed reusable merely because the article is a valid research source.

## Provider routing

`ProviderRouter` reads task routes from `config.json`. Cloud providers are attempted in order. Gemini credentials are tried primary then backup, with duplicate values removed. Failures are classified:

- Authentication/permission: credential is disabled until configuration changes.
- Rate limit/outage/network: credential enters cooldown.
- Invalid request: route fails without pointless repeated retries.
- Local/degraded route: skipped unless explicitly enabled.

State is persisted under `~/.cache/ace/provider-state.json`.

## Caption Director

The caption planner distributes narration timing using the real audio duration when available. It then chooses a presentation mode by purpose and content. Ordinary spoken chunks are kept short; full titles and evidence cards have their own deliberate layouts. It writes:

- `captions/caption-plan.json`
- `captions/accessibility.srt`
- `captions/styled-captions.ass`
- `quality/caption-report.json`

Article/social cards normally suppress duplicate burned text because the source card already contains the exact headline/post.

## Visual Director

Caption phrases are grouped into sentence/idea-level shots. Each shot carries:

- semantic search query
- purpose
- visual type
- mood
- crop focus
- caption mode and position
- transition
- reason for selection

The Visual Intelligence router compares official evidence, demonstrations, original explainers, generated concepts, charts, account assets, licensed stock, typography, and minimal screens. Deterministic scoring rejects forbidden imagery and generic filler; an optional cloud frame judge can inspect sampled frames. If no external resource succeeds, ACE creates a purpose-built visual rather than silently outputting black footage.

After selection, the Caption Director adapts caption visibility and placement to the chosen format. Provider attempts are written as structured trace events, and exact/perceptual fingerprints support duplicate detection.

## Rendering

FFmpeg creates one normalized video segment per shot, concatenates them, mixes normalized narration and optional licensed music, burns ASS captions, and writes a fast-start MP4. Landscape media used in a vertical project is shown over a blurred fill so the complete subject is not destroyed by center cropping.

The validator checks:

- video and audio streams
- output duration and dimensions
- black-frame ratio
- silence ratio
- caption overflow
- missing visuals
- repeated external resources

## Completion states

- `COMPLETE`: every required stage passed without warnings.
- `COMPLETE_WITH_WARNINGS`: all required stages are usable, but a noncritical script, fact, or media warning remains.
- `INCOMPLETE`: one or more required stages is missing or failed.

A script report with status `warning`, no critical problems, and a score at or above the configured gate is valid. This fixes the v1.7 false-incomplete result.

## Visual Intelligence subsystem

The video route uses explicit contracts rather than passing search strings directly to stock providers.

```text
ShotIntent
  → Candidate generators
  → deterministic score
  → optional cloud frame judge
  → VisualDecision
  → shot plan
  → renderer
  → validation
```

The subsystem is located in `src/ace/visual_intelligence/`. Original explainers and candidate artifacts remain separate from the renderer so they can be tested, replaced, or approved independently. Generation state is persisted in `state/generation.sqlite3`; JSON artifacts remain the human-readable interchange format.

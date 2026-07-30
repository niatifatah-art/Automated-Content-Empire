# ADR-0021: Visual Intelligence instead of stock-first assembly

## Status

Accepted for ACE v2.0.2.

## Problem

ACE v2.0.1 could complete a video, but broad media searches sometimes selected imagery that was merely technological rather than semantically correct. The public-Wi-Fi regression contained fire, financial charts, and generic office footage for networking concepts.

## Decision

Every visual shot is now processed through:

```text
ShotIntent
→ Candidate Format Router
→ VisualCandidate set
→ deterministic scoring
→ optional cloud frame judge
→ VisualDecision
→ validation
```

Pexels and Pixabay remain candidates. They are not the default answer for abstract mechanisms, evidence, code, UI demonstrations, comparisons, or data.

ACE generates original explainers for concepts such as encryption, rogue hotspots, passkeys, API routing, partnerships, comparisons, and challenge progress.

## Open-source influences

The design studies ideas from eight audited projects without merging their codebases:

- Video-Automation-Creation: typed stages, timing, FFmpeg and provider patterns
- youtube-automation-agent: persistent state and real/generated/placeholder safety
- n8n-nodes-openai-litellm: request metadata and trace events
- AI-Content-Studio: approvals and restart-from-stage workflows
- Llemonstack: future capability manifests and health checks
- MoneyPrinterV2: future upload preflight and safe retries
- self-hosted-ai-starter-kit: future optional deployment profiles
- youtube-shorts-pipeline: OCR and deduplication concepts only

The implementation is ACE-native and independently written.

## Consequences

- More artifacts are stored per shot.
- Cloud vision calls may add latency and quota usage.
- Deterministic fallback remains available when cloud judgment is unavailable.
- Weak candidates can be repaired without regenerating research, script, or narration.
- Releases must pass the visual benchmark and relevance thresholds.

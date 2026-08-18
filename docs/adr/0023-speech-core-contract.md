# ADR 0023 — Speech Core contract

Status: Accepted as the migration target.

## Context

ACE supports many independent creator accounts and can automate content generation from start to finish. The current voice module chooses providers directly, which is adequate for the existing Kokoro/Piper/OpenAI path but would become a long-term maintenance problem as local TTS, STT, alignment and voice-quality engines grow.

## Decision

ACE will treat speech as an external capability boundary rather than importing Voice Studio UI code or individual engine implementations.

```text
ACE account ── voice_profile_id ──> Speech Core
Voice Studio ─────────────────────> Speech Core
                                      |
                                      +-- TTS engines
                                      +-- STT engines
                                      +-- alignment / VAD / QA
```

### Account binding

Each ACE account may bind a stable `voice.profile_id`. The profile owns engine/model/recipe details outside ACE. The default account policy is `consistency_first` so an established account voice is not silently changed when a new engine or model revision becomes available.

Multiple accounts may share one profile or use different profiles. Language-specific overrides may be added later without changing the contract.

### Compatibility migration

Existing `voice.provider` and `voice.voice_id` remain valid during migration. `ace.voice` continues to work until the Speech Core client reaches feature parity. New provider branches should not be added to ACE unless required to preserve compatibility; new engines belong behind Speech Core.

### Caption timing

When ACE authored the script, the original script remains the caption text source. STT/alignment supplies timings and speech verification. ASR output does not overwrite known script text.

### Privacy

The public Speech Core protocol contains no ACE account names, social handles, platform settings, niches, private paths or publishing credentials. ACE owns the mapping between an account and a voice profile in user data.

### Versioning

Speech requests and artifacts are schema-versioned. A speech artifact records voice-profile revision, engine/model revision, recipe revision, timing, quality and provenance so a generation can be audited and reproduced without coupling ACE to a specific engine implementation.

## Consequences

- Voice Studio and ACE can evolve independently.
- A new TTS/STT engine needs an adapter/certification rather than an ACE rewrite.
- Existing accounts remain functional during migration.
- Consistency becomes an explicit policy rather than an accidental consequence of fixed provider settings.

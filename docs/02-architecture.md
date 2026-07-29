# Architecture

ACE uses replaceable layers:

```text
CLI / Guide
    ↓
Account context and task brief
    ↓
Content catalog and prompts
    ↓
AI engine and task routes
    ↓
Provider adapters
    ↓
Quality, research, speech, resources, editing
    ↓
Generation workspace and status report
```

## Important modules

- `profile.py` — account YAML, migration, version history, rollback, AI compilation.
- `account_context.py` — asks only for critical task-specific gaps.
- `ai.py` — routes local/cloud models, fallbacks, free-only policy, and Smart Memory.
- `content.py` — candidates, selection, review, extras, isolated generation folders.
- `quality.py` and `fact_check.py` — script and factual-risk gates.
- `speech.py` and `engines/voice.py` — spoken rewrite, pronunciation, and modular TTS.
- `resources_engine.py` — account media, reusable stock, licensing, and references.
- `editing.py` — timelines, subtitles, branded fallback visuals, FFmpeg, and validation.
- `generation_status.py` and `autopilot.py` — completion contracts and repair.

The static catalogs are editable configuration. Provider discovery is dynamic so ACE is not limited to model names known when the release was built.

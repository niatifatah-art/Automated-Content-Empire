# Introduction

Automated Content Empire is a persistent content-production environment, not a one-off prompt wrapper. It remembers who an account is, adapts that identity to each platform, creates isolated generation folders, and validates important stages before reporting completion.

The v1.7 pipeline is:

```text
Account source of truth
→ task-specific brief
→ research references
→ candidate generation
→ selection and review
→ factual-risk and script-quality gates
→ TTS-safe spoken script
→ account voice
→ licensed/account visuals or branded fallback
→ subtitles and editing plan
→ FFmpeg render
→ media validation
```

ACE is local-first but not local-only. Local Ollama and TTS engines can provide a zero-subscription baseline, while cloud providers remain optional quality or speed upgrades.

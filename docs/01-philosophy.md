# ACE Design Philosophy

ACE keeps the original rule:

> Build engines, not isolated features.

## One responsibility per engine

- Configuration resolves settings.
- Profiles define account identity.
- Catalogs define platforms, content types, and named models.
- Prompts define the work requested from a model.
- Provider adapters implement external protocols.
- AI routing chooses primary and fallback models.
- Memory manages local model lifetime.
- Content coordinates candidates, selection, review, and extras.
- Storage creates reproducible workspaces.
- Assets manage media owned by the account.
- Resources discover media and record licenses.
- Voice generates narration.
- Editing creates timelines and subtitles.
- Rendering turns the package into baseline media.

## Models are configuration, not code

A content function never hard-codes Gemini, Ollama, or Claude. It asks for a task such as `script`, `selection`, or `review`; the configured route decides which model to use.

```text
script
  ↓
gemini/gemini-3.6-flash
  ↓ fallback
ollama/qwen3:8b
```

The same route can be replaced with an alias or any exact provider model ID.

## Local first, quality aware

Local-first is a preference, not a refusal to use cloud capabilities. ACE can be run free/local, cloud-assisted, or mixed. Missing optional services should downgrade the route or skip an optional stage without destroying completed work.

## Identity is global; platform behavior is local

A profile owns personality and brand voice. Platform rules own only delivery adaptation. This avoids producing six unrelated personalities for six social platforms.

## Security is structural

API keys are never part of source-controlled model configuration. Secrets are loaded from a protected file outside the repository or from process environment variables. Status commands mask values.

## Reproducibility over hidden magic

Every generation stores its profile snapshot, prompt, model/provider metadata, candidate set, evaluation, selected version, licenses, and edit plan. Automatic decisions remain inspectable.

## Honest degradation

ACE should say what it skipped and why. It should never claim that a thumbnail image, premium voice, authoritative research, or final render exists when only a brief or fallback was produced.

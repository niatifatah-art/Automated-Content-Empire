# ACE v1.7.0 Final Test Report

Date: 2026-07-29
Release: Automated Content Empire 1.7.0

## Result

The tested ACE v1.7.0 source, package wheel, creator CLI, account system, Autopilot pipeline, Smart Memory lifecycle, TTS preparation, editing package, subtitle burning, branded visual fallback, and FFmpeg validation passed the checks listed below.

This report does **not** claim that the software is bug-free or that every third-party service was live-tested. External services require real credentials, network access, quotas, provider availability, and accepted terms.

## Automated source tests

```text
45 passed
```

Coverage includes:

- creator and compatibility CLI parsing;
- manual, assisted, and Autopilot flags;
- persistent account YAML, history, rollback, and safe 0.3.x upgrade backups;
- critical account-context checks;
- content-history similarity checks;
- dynamic installed-model selection;
- free/local-only route enforcement;
- model catalog search and readiness;
- TTS artifact cleanup and pronunciation normalization;
- precise-claim fact-check blocking without sources;
- incomplete-generation diagnostics;
- `COMPLETE_WITH_WARNINGS` reporting;
- provider request/response parsing and fallback behavior;
- voice routing, lazy Kokoro behavior, and audition cleanup;
- configuration, catalog, storage, content, and project compatibility.

Command used:

```bash
PYTHONPATH=src pytest -q
```

## Built-in release self-test

All six checks passed:

```text
configuration: ok
commands: ok
models: ok
TTS preparation: ok
license classifier: ok
real FFmpeg render: ok
```

Commands:

```bash
ace test full
ace release verify --report
```

## Focused-help matrix

Twenty-six help paths were executed successfully, including:

```text
ace --help
ace guide --help
ace create --help
ace account build --help
ace models search --help
ace models test --help
ace voice audition --help
ace resources find --help
ace edit render --help
ace release verify --help
```

## AI-built account test

A local Ollama-compatible test service returned a structured account draft. ACE:

- compiled it into `account.yaml`;
- preserved identity, humor, audience, platforms, languages, pillars, and visual style;
- set it active;
- reloaded it through the YAML layer;
- passed `ace account check`.

Result:

```text
AI_PROFILE_E2E_OK
```

## Source-tree Autopilot end-to-end test

A full local test used:

- a controlled Ollama-compatible HTTP service;
- one dynamically discovered installed model (`qwen2.5:latest`);
- a controlled Piper-compatible executable producing real WAV audio;
- real FFmpeg and ffprobe;
- no reusable external media, forcing ACE's branded visual fallback.

Verified outputs:

```text
selected.md
script/tts-ready.txt
voice/narration.wav
subtitles/subtitles.srt
editing/edit-plan.json
exports/final.mp4
quality/script-report.json
quality/fact-report.json
quality/voice-report.json
quality/media-report.json
autopilot-report.json
```

The MP4 contained real video and audio streams, subtitles were burned, branded fallback visuals avoided a black render, the requested and actual voices matched, media validation passed, and the generation reached a complete state with the expected factual-source warning.

Smart Memory result:

```text
18 related model calls
1 unload at pipeline end
```

## All-accounts Autopilot test

The real `--all-profiles` path was executed for two eligible accounts with different primary languages.

Verified:

- two independent generation folders;
- separate account snapshots;
- English and French routing remained distinct;
- one Smart Memory unload per account pipeline;
- no copying of one account's output folder into the other.

Result:

```text
ALL_PROFILES_E2E_OK folders=2 languages=en,fr unloads=2
```

## Wheel build and isolated installation

The final wheel was built from the tested source and installed into a new virtual environment without using the source tree.

Verified:

- `ACE 1.7.0`;
- packaged JSON catalogs and all prompt resources;
- `ace init` and `ace init --upgrade`;
- fallback account construction without a live model;
- readable account YAML;
- `ace account check`;
- `ace plan`;
- built-in full self-test;
- `pip check` with no broken requirements;
- protected `secrets.env` permissions of `0600`.

## Installed-wheel Autopilot end-to-end test

The actual installed `ace` executable—not `PYTHONPATH=src`—ran the complete YouTube Short Autopilot path against the controlled local services.

Verified:

```text
candidates and automatic selection
supporting extras
script review
quality gate
research record
factual-risk gate
TTS-safe spoken rewrite
account voice enforcement
real WAV narration
branded visual fallback
subtitles
editing timeline
real FFmpeg final render
black-frame and silence checks
stage-by-stage status
```

Result:

```text
FINAL_INSTALLED_E2E_OK calls=18 unloads=1 status=COMPLETE_WITH_WARNINGS
```

The warning was expected because no live research source was available in the controlled offline run. The script did not contain unsupported precise statistics or direct quotations, so the factual gate was non-blocking.

## Final source ZIP retest

The clean source ZIP was extracted into a new directory after packaging. The extracted copy passed:

```text
45 automated tests
Python compilation
ACE 1.7.0 version check
built-in full self-test
archive hygiene check (no secrets, virtual environment, Git metadata, bytecode, or build cache)
```

Result:

```text
ZIP_RETEST_OK
ARCHIVE_CLEAN_OK
```

## Dependency and package audit

The core package has no mandatory third-party Python dependency. Optional imports map to declared extras:

```text
PyYAML             -> .[yaml]
Kokoro/numpy/soundfile -> .[voice]
Pocket TTS/scipy   -> .[pocket-tts]
pytest             -> .[test]
```

The internal YAML compatibility layer allows the core wheel to create, edit, and reload readable account YAML without requiring PyYAML.

## Test classification

### Locally and genuinely executed

- Python compilation;
- 45 automated tests;
- all listed help commands;
- account YAML creation and migration logic;
- secure secret-file creation and permissions;
- source and installed CLI workflows;
- model routing against a controlled local HTTP server;
- Smart Memory unload behavior;
- WAV generation through a Piper-compatible executable;
- subtitle creation and burning;
- actual FFmpeg encoding and ffprobe inspection;
- black-frame and silence validation;
- wheel build and isolated installation;
- `pip check`.

### Contract or mock tested

- Gemini request/response behavior;
- Anthropic request/response behavior;
- OpenAI-compatible chat and Responses behavior;
- OpenRouter/LM Studio/vLLM-compatible routing;
- Ollama errors, fallback, discovery, and unload requests;
- Kokoro/Pocket TTS/OpenAI TTS adapter behavior;
- resource license classification and provider parsing;
- API failures, missing keys, unavailable models, and fallback paths covered by tests.

### Not live-tested in the release environment

- paid Gemini, OpenAI, Anthropic, OpenRouter, or OpenAI TTS requests;
- a real LM Studio or vLLM server;
- real Pocket TTS, Kokoro, or Piper model inference;
- live Openverse, Wikimedia Commons, Pexels, Pixabay, or Unsplash downloads;
- every possible provider model or third-party API version.

These items depend on credentials, installed models, subscriptions, network access, quota, hardware, and external service behavior. ACE reports those capabilities as ready, missing, disabled, unreachable, or untested instead of claiming success.

## Final conclusion

The delivered ACE v1.7.0 release passed the implemented source tests, self-tests, help checks, account compiler test, single-account Autopilot test, all-accounts test, wheel build, isolated installation, and installed-CLI Autopilot render test. The release contains strong validation and repair mechanisms, but production users should still review breaking news, high-stakes factual claims, licensing decisions, and final media before publication.

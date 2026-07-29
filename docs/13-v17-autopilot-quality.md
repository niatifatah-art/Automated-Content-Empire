# ACE v1.7 Autopilot and quality gates

Autopilot performs routine decisions but stops for critical problems such as missing account identity, disabled target platforms, unsupported precise factual claims, missing account voice for a required video, or failed final-media validation.

```bash
ace create youtube short "Topic" --auto
ace auto youtube short "Topic"
ace fix last
```

Quality artifacts include:

```text
quality/script-report.json
quality/fact-report.json
quality/tts-report.json
quality/voice-report.json
quality/media-report.json
status.json
autopilot-report.json
```

`COMPLETE`, `COMPLETE_WITH_WARNINGS`, and `INCOMPLETE` are based on a content-type completion contract, not merely the existence of a file. Video completion requires script quality, factual-risk handling, TTS preparation, narration, a visual route, subtitles, an edit plan, final render, and media validation.

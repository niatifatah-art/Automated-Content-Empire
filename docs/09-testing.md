# Testing

Developer tests:

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src/ace
```

Installed-product self-tests:

```bash
ace test quick
ace test commands
ace test models
ace test voice
ace test resources
ace test render
ace test full --report
ace release verify --report
```

The real render self-test creates a synthetic narration WAV, burns subtitles into an FFmpeg preview, and validates audio/video streams. Live cloud calls are not claimed unless credentials and network access are actually present.

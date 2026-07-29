# Providers and models

Text adapters include Ollama, Gemini, Anthropic, and OpenAI-compatible endpoints. OpenAI, OpenRouter, LM Studio, and vLLM use the OpenAI-compatible adapter with different configuration.

```bash
ace models search gemini
ace models search qwen
ace models discover all
ace models ready
ace models test --all
ace models use script local-balanced
ace models use review cloud-balanced
```

Model states include `READY`, `NOT INSTALLED`, `KEY MISSING`, `DISABLED`, `UNREACHABLE`, `UNTESTED`, and `UNCONFIGURED`.

API keys are stored in `~/.config/ace/secrets.env` and can be configured through `ace guide` or `ace secrets edit`.

Smart Memory keeps the same local model loaded across adjacent steps, unloads before a different local model when necessary, and unloads local models when the pipeline finishes or fails.

```bash
ace memory status
ace memory mode smart
ace memory unload
```

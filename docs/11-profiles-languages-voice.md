# Accounts, languages, and voice

One account is one identity shared across its enabled platforms. Platform adaptation changes format, not personality.

```bash
ace new
ace account build --name Brand "Plain-language description"
ace account show
ace account edit
ace account check
ace account history
ace account rollback 1
```

Per-generation language overrides:

```bash
ace create youtube short "Topic" -eng
ace create instagram reel "Topic" -fr
ace create tiktok short "Topic" -ar
```

Localization is a model-assisted rewrite that preserves intention and account identity; it is not blind word substitution.

Voice routes are account-specific:

```bash
ace voice providers
ace voice audition --provider kokoro
ace voice audition --provider pocket_tts
ace voice status
```

Arabic prefers natural broadly understood social Arabic and falls back to spoken standard Arabic when the selected provider cannot support the requested register. TTS provider language support is checked separately from the text-localization model.

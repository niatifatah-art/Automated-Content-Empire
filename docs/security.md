# Security, credentials, evidence, and licensing

## Secrets

Secrets belong only in `~/.config/ace/secrets.env` or a portable workspace’s `config/secrets.env`. ACE creates the file with mode `0600`. The project `.gitignore` excludes secrets, local state, caches, virtual environments, and generated content.

Supported secret names include:

```text
GEMINI_API_KEY_PRIMARY
GEMINI_API_KEY_BACKUP
GEMINI_API_KEY
PEXELS_API_KEY
PIXABAY_API_KEY
OPENVERSE_ACCESS_TOKEN
OPENAI_API_KEY
OPENROUTER_API_KEY
GIPHY_API_KEY
TENOR_API_KEY
```

Two Gemini keys are for authorized resilience, replacement, or separate legitimate environments. ACE must not be used to create accounts or rotate credentials to evade quotas or provider restrictions.

## Source trust

ACE distinguishes:

- official primary documents
- regulators, filings, and research
- reputable reporting
- specialist creators and developers
- public reactions
- anonymous claims, rumors, satire, and memes

A public reaction can appear as context while receiving zero evidence weight. Breaking claims may require a primary source or multiple independent credible sources.

## Screenshots

Official-domain screenshots may be captured automatically when browser support is installed. Nonofficial captures require explicit approval. Captures preserve the URL, time, hash, and modification record. Cropping and resizing are allowed; changing the source wording is not.

## Generated media

Generated illustrations are stored with provider, model, prompt, origin, timestamp, and usage metadata. They must never impersonate evidence. ACE blocks workflows intended to create fake posts, fake news pages, fake quotations, or fabricated documentary screenshots.

## Memes and GIFs

Account-owned, ACE-generated, public-domain, and appropriately licensed meme material is preferred. Internet templates, GIPHY, and Tenor results remain approval-gated candidates. Their availability through an API does not automatically grant commercial video-reuse rights.

## Publishing

Publishing integrations are not active in v2.0.1. `prepare`, `approve`, and `schedule` create records only. The final approval requirement cannot be bypassed by Autopilot.

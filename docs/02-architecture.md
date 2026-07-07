# ACE Architecture

ACE follows a layered architecture.

Each layer has a single responsibility.

```
                User
                  │
                  ▼
             ACE CLI
                  │
                  ▼
          Command Dispatcher
                  │
                  ▼
        ┌───────────────────┐
        │   Content Engine   │
        └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │   Prompt Engine    │
        └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │      AI Engine     │
        └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │    AI Provider     │
        │     (Ollama)       │
        └───────────────────┘
                  │
                  ▼
        ┌───────────────────┐
        │  Storage Engine    │
        └───────────────────┘
                  │
                  ▼
            Markdown Files
```

---

# Layers

## CLI

Receives commands from the user.

The CLI should never contain business logic.

---

## Command Dispatcher

Routes commands to the appropriate engine.

---

## Content Engine

Coordinates content generation.

It does not communicate directly with language models.

---

## Prompt Engine

Loads prompt templates.

Responsible only for prompt management.

---

## AI Engine

Communicates with language models.

Responsible only for AI interaction.

---

## AI Provider

The implementation currently uses Ollama.

Future providers may include:

- OpenAI
- Gemini
- LM Studio
- vLLM
- Others

The rest of the architecture should not depend on a specific provider.

---

## Storage Engine

Stores generated content.

Future versions may support:

- Markdown
- JSON
- SQLite
- PostgreSQL
- Cloud Storage

The rest of the project should not depend on the storage implementation.

---

# Design Rules

- Every layer has one responsibility.
- Layers communicate downward.
- Engines remain independent.
- Providers are replaceable.
- Features are built from engines.

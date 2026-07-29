# ACE Architecture Summary

ACE is a local-first, CLI-first content operating system built from replaceable engines.

Core rules:

- One profile is one consistent account identity across platforms.
- Models are named, editable task routes rather than hard-coded calls.
- Local and cloud providers share one AI interface.
- Smart Memory keeps at most one managed local model through related steps and unloads it afterward.
- Platforms and deliverable types are catalog data.
- API keys live in protected external secret storage.
- Every generation is an isolated, reproducible folder.
- Research references are separate from publishable media.
- Only license-compatible resources reach editing.
- Editing packages remain useful when optional rendering or voice is unavailable.
- Every automatic decision should leave inspectable metadata.

Detailed architecture: [02-architecture.md](02-architecture.md).

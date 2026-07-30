# Contributing to ACE

ACE is organized around explicit production stages. A change should improve a measurable capability without silently weakening factual quality, provenance, or output validation.

## Before coding

1. Identify one concrete ACE problem.
2. Record the architectural decision in `docs/adr/` when it changes a subsystem.
3. Check third-party licenses before adapting an idea.
4. Prefer clean-room reimplementation of engineering patterns over merging unrelated codebases.
5. Add a benchmark or regression test before changing production behavior.

## Visual Intelligence rules

Every selected visual must be traceable to:

- a `ShotIntent`
- one or more `VisualCandidate` records
- a `VisualScore`
- a `VisualDecision`
- source and license metadata

Stock footage must not pass merely because it has generic technology tags. Evidence must be truthful, official where required, and separated from illustration.

## Required checks

```bash
PYTHONPATH=src python -m compileall -q src/ace
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m ace.main visuals benchmark
PYTHONPATH=src python -m ace.main test quick
```

Before a release:

```bash
PYTHONPATH=src python -m ace.main test full
python -m build
```

Never commit API keys, user account state, generated media, virtual environments, cache directories, or provider responses containing private data.

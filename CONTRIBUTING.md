# Contributing to ACE

Before adding code, identify the engine that owns the responsibility.

A contribution should include:

1. readable implementation
2. automated tests
3. current documentation
4. explicit fallback/error behavior
5. no duplicated provider or platform logic
6. no API keys or user profile data in Git
7. provenance and license handling for resource providers

Run before submitting:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src/ace
```

- Provider protocols: `src/ace/providers/`
- Platform behavior: `content_catalog.json`
- Named model conveniences: `model_catalog.json`
- Prompt wording: `prompts/`
- CLI parsing: `src/ace/cli.py`
- Execution: `src/ace/commands.py`

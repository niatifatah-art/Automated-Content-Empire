# Folder structure

## Application source

```text
src/ace/
├── cli.py, commands.py, guide.py
├── profile.py, account_context.py, account_memory.py
├── ai.py, models.py, memory.py
├── content.py, quality.py, fact_check.py, research.py
├── speech.py, assets.py, resources_engine.py, editing.py
├── generation_status.py, autopilot.py, selftest.py
├── providers/
├── engines/
└── resources/
```

## User configuration

```text
~/.config/ace/
├── config.json
├── content_catalog.json
├── model_catalog.json
├── secrets.env
├── prompts/
└── accounts/<slug>/account.yaml
```

## User data

```text
~/.local/share/ace/
├── accounts/<slug>/assets/
├── content/<slug>/<platform>/<type>/<run>/
├── projects/
└── models/
```

Every content run stores candidates, selection data, account snapshots, research, quality reports, narration, reusable resources, license manifests, subtitles, edit plans, exports, and status metadata as applicable.

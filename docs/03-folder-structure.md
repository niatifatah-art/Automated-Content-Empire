# Project Structure

ACE follows the "src layout" project structure.

```
Automated-Content-Empire/

├── config/
│   └── config.json
│
├── data/
│   └── content/
│
├── docs/
│
├── logs/
│
├── prompts/
│   ├── linkedin.txt
│   └── youtube.txt
│
├── scripts/
│
├── src/
│   └── ace/
│       ├── ai.py
│       ├── cli.py
│       ├── commands.py
│       ├── config.py
│       ├── content.py
│       ├── doctor.py
│       ├── prompt.py
│       ├── storage.py
│       └── main.py
│
├── tests/
│
├── workflows/
│
├── pyproject.toml
├── README.md
└── LICENSE
```

---

# Directory Overview

## src/

Contains the application source code.

No documentation or data should be stored here.

---

## prompts/

Stores prompt templates.

Keeping prompts outside the Python code makes them easier to edit and maintain.

---

## config/

Stores configuration files.

Configuration should never be hardcoded.

---

## data/

Stores generated content and temporary project data.

---

## docs/

Contains all project documentation.

Documentation is considered part of the project.

---

## tests/

Contains automated tests.

---

## logs/

Stores runtime logs.

---

## workflows/

Future automation workflows (n8n and others).

---

## scripts/

Utility scripts used during development.

---

# Why Use the src Layout?

Separating source code from the project root prevents accidental imports and follows modern Python packaging practices.

It also makes packaging and testing more reliable.

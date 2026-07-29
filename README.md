# Automated Content Empire — ACE v1.7.0

ACE is a Linux-friendly, account-aware command-line content production system. One ACE account represents one recognizable brand identity across YouTube, TikTok, Instagram, Facebook, X, and LinkedIn. ACE adapts format and pacing for each platform without silently changing the account's personality, audience, language rules, or voice.

## What v1.7 adds

- Human-readable `account.yaml` as the permanent source of truth for every account.
- AI-assisted account/profile compilation from a plain-language description.
- Manual, assisted, and Autopilot creation modes.
- A simplified creator CLI: `ace create`, `ace guide`, `ace check`, `ace status`, `ace fix`, `ace models`, and `ace voice`.
- Focused nested help through `ace <command> --help`.
- Local and cloud model routing with live discovery and named aliases.
- Smart local-model RAM management and free/local-only execution.
- Multiple candidate generation, automatic scoring, review, and quality retries.
- Research references, factual-risk checks, and explicit claim warnings.
- TTS-safe spoken-script preparation before narration.
- Modular Pocket TTS, Kokoro, Piper, and OpenAI TTS routes.
- Automatic reusable-media search with strict license classification.
- Branded motion-graphics fallback when no external visual is safe to use.
- Subtitle generation and burning, FFmpeg rendering, black-frame checks, and silent-audio checks.
- Stage-by-stage status, repair, self-test, and release-verification commands.

## Install on Linux Mint

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg libsndfile1 espeak-ng

unzip Automated-Content-Empire-1.7.0.zip
cd Automated-Content-Empire-1.7.0

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

ace init
ace check
ace new
```

Voice extras:

```bash
python -m pip install -e ".[voice]"       # Kokoro
python -m pip install -e ".[pocket-tts]"  # Pocket TTS
python -m pip install -e ".[test]"        # pytest for the full source test suite
```

## Upgrade from ACE 0.3.x

Back up persistent state, install v1.7 in its own folder, then run the safe upgrader:

```bash
cp -a ~/.config/ace ~/.config/ace.backup-before-v17
cp -a ~/.local/share/ace ~/.local/share/ace.backup-before-v17
ace init --upgrade
ace account show
ace check
```

`ace init --upgrade` keeps accounts, secrets, model choices, and other user settings. It backs up editable catalogs and prompts before installing the v1.7 versions. Avoid `ace init --force` during a normal upgrade because `--force` intentionally replaces shipped defaults.

## Creator workflow

```bash
ace create youtube short "Why passkeys matter" --manual
ace create youtube short "Why passkeys matter" --assisted
ace create youtube short "Why passkeys matter" --auto
ace create youtube short "Why passkeys matter" --auto --all-profiles
```

Shortcuts remain available:

```bash
ace youtube short "Why passkeys matter" --auto
ace tt short "A Python mistake beginners make" --assisted
ace ig reel "Linux gaming is changing" --manual
```

The modes mean:

- **manual** — asks at every meaningful decision.
- **assisted** — accepts normal recommendations and pauses at major checkpoints.
- **auto** — completes the pipeline and interrupts only for critical failures.

Set the account default once:

```bash
ace mode assisted
ace mode auto
```

## Guided help

```bash
ace guide
ace guide "I made a video without visuals"
ace voice audition --help
ace models search --help
```

`ace guide` can walk through first content, models, protected API keys, voice setup, reusable visuals, incomplete videos, Autopilot, and readiness checks.

## Accounts as the source of truth

Normal Linux paths:

```text
~/.config/ace/
├── config.json
├── model_catalog.json
├── content_catalog.json
├── secrets.env                 # chmod 0600
└── accounts/
    └── fatah/
        ├── account.yaml
        ├── history/
        ├── voice-sample.wav
        └── voice-audition.json

~/.local/share/ace/
├── accounts/fatah/assets/
└── content/fatah/<platform>/<type>/<generation>/
```

Build an account with an LLM:

```bash
ace account build --name Fatah \
  "Technology, gaming, cybersecurity and programming explained in a fun way"
```

Edit, validate, version, or roll back it:

```bash
ace account show
ace account edit
ace account check
ace account history
ace account rollback 2
```

ACE asks for missing account information only when it is critical to the current request. New answers are stored in the account source of truth rather than asked repeatedly.

## Models

```bash
ace models search qwen
ace models search gemini
ace models installed
ace models ready
ace models recommend
ace models discover ollama
ace models test ollama qwen2.5:latest
ace models use script local-balanced
```

Named aliases include `local-fast`, `local-balanced`, `cloud-fast`, `cloud-balanced`, and `cloud-quality`. `ollama/auto` resolves to the best suitable model already installed on the machine.

The bundled catalog is editable and intentionally not authoritative forever. Use live discovery for the provider's current model list.

## Protected API keys

```bash
ace guide              # choose Configure API keys
ace secrets edit
ace secrets status
```

Real keys live in `~/.config/ace/secrets.env`, outside the project and protected with mode `0600`. ACE never commits this file and uses hidden terminal input in the guide.

## Voice and natural speech

```bash
ace voice providers
ace voice audition --provider kokoro -eng
ace voice audition --provider pocket_tts -fr
ace voice prepare last
ace voice generate last
ace voice test
ace voice status
```

ACE keeps one selected account voice, creates a separate TTS-ready script, normalizes URLs, headings, stage directions, quotation artifacts, abbreviations, and pronunciation rules, then verifies that the requested and actual voices match.

## Visual resources and final video

```bash
ace assets add ~/Videos/clip.mp4 --tags passkeys,security
ace resources find last --query "passkeys cybersecurity" --limit 8
ace resources list last
ace edit package last
ace edit render last
ace status last
ace fix last
```

Research references are not treated as publishable media. ACE automatically permits only account-owned media and compatible reusable licenses. If no safe stock or account asset is found, the FFmpeg renderer creates a visible branded motion-text fallback instead of a black video.

## Completion and diagnostics

```bash
ace check
ace status last
ace fix last
ace test quick
ace test full --report
ace release verify --report
```

A video is not complete merely because an MP4 exists. ACE checks the script, factual risk, TTS preparation, narration, visual route, subtitles, edit plan, video/audio streams, black-frame ratio, and silence ratio. Results are reported as `COMPLETE`, `COMPLETE_WITH_WARNINGS`, or `INCOMPLETE`.

## Platforms and content types

The editable catalog currently describes 41 content types across:

- YouTube
- TikTok
- Instagram
- Facebook
- X
- LinkedIn

Run:

```bash
ace content list
ace content list youtube
```

## Honest boundaries

- Live third-party APIs require the user's own keys, connectivity, quota, and accepted provider terms.
- ACE records license metadata but cannot give legal advice or guarantee that every real-world use is lawful.
- Automatic factual checking is a safety gate, not a substitute for reviewing high-stakes or breaking-news claims.
- Local image diffusion is not bundled because it is unsuitable as a default for modest hardware; ACE uses account assets, reusable stock, configured external providers, and branded FFmpeg visuals.

Read the documentation index at [`docs/README.md`](docs/README.md).

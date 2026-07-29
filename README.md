# Automated Content Empire — ACE v2.0.1

ACE is a cloud-first, evidence-aware content production system for YouTube, TikTok, Instagram, Facebook, X, and LinkedIn. It researches a topic, writes and reviews a script, maps important claims to sources, produces narration, plans shot-specific visuals, directs captions adaptively, and renders a validated video with FFmpeg.

ACE v2 is designed around one principle: **finishing a file is not enough; the result must remain factual, visually intentional, legally traceable, and recognizable as the creator’s brand.**

## v2.0.1 reliability fixes

- Existing v1/v2 accounts are automatically migrated with the adaptive `editing` block.
- Gemini quota cooldowns are tracked per credential **and model**, so a 3.6 Flash limit does not block 3.5 Flash or Flash-Lite.
- Cloud fallback order now tries the backup Gemini credential, then other Gemini cloud models, before any local degraded route.
- Gemini 3.5/3.6 requests no longer send deprecated sampling parameters.
- Credential tests use enough output budget for thinking-enabled models.
- Empty caption, visual, and edit inspections report `not_run` instead of a false `passed`.
- Failed early generations preserve and report the real research-source count.


## What changed in v2

- Cloud-quality models are primary for research, writing, verification, creative direction, and quality control.
- Two authorized Gemini credentials can be configured as primary and backup.
- Local Ollama models are no longer silently treated as equivalent to cloud models; they require explicit degraded-mode consent for quality-sensitive work.
- Research sources, claims, contradictions, article evidence, social reactions, reusable media, and generated visuals are stored separately.
- Official webpages can be captured as evidence; nonofficial screenshots require approval.
- Social posts may improve the story, but opinions and viral reactions never become factual proof by themselves.
- The Caption Director chooses between no visible caption, short phrase, keyword, full title, source headline, code panel, statistic, challenge counter, or call to action.
- Caption text is dynamically fitted into safe areas with a two-line limit and overflow validation.
- The Visual Director creates a semantic search query per shot, ranks stock media, preserves vertical framing, and generates an original fallback instead of using black frames.
- Existing and generated memes are supported with tone checks, attribution metadata, and approval requirements for internet material.
- Narration is normalized, optionally mixed with licensed music, and checked for silence.
- Completion logic correctly accepts high-scoring noncritical warnings as `COMPLETE_WITH_WARNINGS`.
- Publishing remains approval-gated: ACE may prepare and schedule a package, but never publishes automatically.

## Install on Linux Mint / Ubuntu

System tools:

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg libsndfile1 espeak-ng fonts-dejavu-core
```

Create a clean environment:

```bash
unzip Automated-Content-Empire-2.0.1.zip
cd Automated-Content-Empire-2.0.1

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

Install Kokoro narration support:

```bash
python -m pip install -e ".[voice]"
```

Optional official-page browser capture:

```bash
python -m pip install -e ".[browser]"
playwright install chromium
```

Developer/test dependencies:

```bash
python -m pip install -e ".[test]"
```

## Upgrade an existing ACE installation

Your accounts, API keys, generated content, and account assets are stored outside the source folder. Back them up before upgrading:

```bash
cp -a ~/.config/ace ~/.config/ace.backup-before-v2
cp -a ~/.local/share/ace ~/.local/share/ace.backup-before-v2
cp -a ~/.cache/ace ~/.cache/ace.backup-before-v2 2>/dev/null || true
```

Activate the venv in which the old `ace` command is installed, then install v2:

```bash
source /path/to/your/old/project/.venv/bin/activate
cd Automated-Content-Empire-2.0.1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[voice]"
ace init --upgrade
ace account check
ace check --offline
```

`ace init --upgrade` merges new defaults into the existing configuration while preserving user values. Do not use `--force` during a normal upgrade.

## First-time setup

```bash
ace init
ace new \
  --name Fatah \
  --description "Technology, gaming, cybersecurity and programming explained in a fun and credible way" \
  --niche technology \
  --language en \
  --platforms youtube,tiktok,instagram,facebook,x,linkedin
```

The generated account file is editable:

```bash
ace account edit
ace account check
```

A complete Fatah account example is in `examples/account.yaml`.

## Protected API keys

Open the protected secrets file:

```bash
ace secrets edit
```

Use this structure:

```dotenv
GEMINI_API_KEY_PRIMARY=your_primary_authorized_key
GEMINI_API_KEY_BACKUP=your_backup_authorized_key
PEXELS_API_KEY=your_pexels_key
PIXABAY_API_KEY=your_pixabay_key

# Optional providers
OPENVERSE_ACCESS_TOKEN=
OPENAI_API_KEY=
OPENROUTER_API_KEY=
GIPHY_API_KEY=
TENOR_API_KEY=
```

Never paste keys into chat, source code, screenshots, or Git commits. ACE stores them in `~/.config/ace/secrets.env` with mode `0600`.

Two Gemini credentials are supported for legitimate primary/backup resilience. ACE does not implement quota-evasion rotation. Rate-limit responses trigger cooldown, backoff, cache reuse, model/provider failover, or a clear stop.

Test credentials:

```bash
ace secrets status
ace credentials status
ace credentials test --provider gemini --model gemini-3.6-flash
ace quota status
```

## Cloud-first model policy

Important tasks use strong cloud routes first:

```text
Gemini primary credential
  → Gemini backup credential
  → another configured cloud provider
  → stop clearly
```

Ollama is available only as an explicit degraded fallback:

```bash
ace create youtube short "Topic" --auto --both --allow-degraded
```

Without `--allow-degraded`, ACE will not silently replace cloud research, writing, fact checking, or creative direction with a small local model.

Inspect and modify routes:

```bash
ace models routes
ace models search cloud
ace models use script cloud-balanced
ace models test gemini gemini-3.6-flash
```

## Create a complete video

```bash
ace create youtube short \
  "Why passkeys are safer than passwords" \
  --auto \
  --both
```

Useful controls:

```bash
--preview             Render a low-resolution preview
--resources none      Use generated/evidence visuals without stock searches
--no-voice            Create the package without narration
--provider gemini     Force one provider
--model MODEL         Force one model
--no-fallback         Stop after the selected provider/model fails
--allow-degraded      Permit explicit local emergency mode
--instructions TEXT   Add content-specific constraints
--variants 1|3|5|10   Candidate count
```

After generation:

```bash
ace status last
ace edit inspect last
ace recent --open
```

Open the final video:

```bash
xdg-open "$(ace recent)/exports/final.mp4"
```

## Evidence-aware research

ACE keeps references separate from reusable media.

```bash
ace research collect last --query "Nvidia partnership"
ace research verify last
ace research show last
```

Add an article or official announcement:

```bash
ace sources add "ARTICLE_URL" last
ace evidence build last
```

Add a social post:

```bash
ace sources add-post "POST_URL" last
ace evidence build last
```

Capture an official page:

```bash
ace evidence capture "OFFICIAL_URL" last
```

Capture a nonofficial page only after review:

```bash
ace evidence capture "URL" last --approve
```

Evidence records include the original URL, publisher, date when available, source type, credibility classification, official-domain status, retrieval time, and a hash of the captured artifact.

## Visual resources

Supported routes include:

- Account-owned files
- Pexels
- Pixabay
- Openverse
- Wikimedia Commons
- ACE article and social-post cards
- Cloud-generated images
- Original ACE diagrams and fallback graphics
- Approved meme/GIF candidates

Search without downloading:

```bash
ace resources find last \
  --query "smartphone biometric authentication" \
  --type video \
  --limit 8
```

Download and register selected results:

```bash
ace resources find last \
  --query "smartphone biometric authentication" \
  --type video \
  --limit 8 \
  --download
```

Plan visuals per spoken moment:

```bash
ace visuals plan last
ace visuals collect last
ace visuals inspect last
```

Add account-owned media:

```bash
ace assets add ~/Videos/my-clip.mp4 --tags "phone,biometric,security"
ace assets list
```

## Adaptive captions

Visible captions and accessibility subtitles are different outputs. Accessibility subtitles remain available even when the Caption Director intentionally leaves the screen clean.

```bash
ace captions plan last
ace captions inspect last
ace captions preview last
```

Possible visible modes:

```text
none
short_phrase
keyword
full_title
article_headline
social_post
quote_card
code_panel
statistic
challenge_counter
call_to_action
```

ACE limits ordinary captions to two lines, fits text to the safe width, adapts font size, and blocks a final render when overflow is detected.

## Editing styles

```bash
ace edit styles
ace edit style set technical_dynamic
ace edit preview last
ace edit inspect last
ace edit rerender last --style gaming_hype
```

Included styles:

- `technical_dynamic`
- `clean_documentary`
- `gaming_hype`
- `challenge`
- `serious_technical`
- `playful_tech`
- `adaptive`

Adaptive mode selects the mood from the topic and script. Serious incidents suppress humor; gaming, challenge, Linux, and programming topics can use faster pacing, controlled memes, and light self-aware cringe.

## Memes

ACE-generated meme cards are account-owned output:

```bash
ace memes generate last \
  --setup "Linux users after fixing Wi-Fi:" \
  --punchline "It only took three kernels"
```

Search configured meme providers:

```bash
ace memes search "confused developer" --limit 10
ace memes fit "a serious security breach" --mood serious_technical
```

Internet memes, GIPHY results, and Tenor results are candidates, not automatically copyright-cleared media. ACE records attribution and approval requirements and prefers an original remake when reuse rights are uncertain.

## Cloud-generated images

```bash
ace images generate last \
  "A clean vertical concept illustration of passkey authentication, no logos, no text" \
  --aspect-ratio 9:16
```

Generated images are stored with provider, model, prompt, timestamp, and origin metadata. ACE does not generate fake screenshots, fake articles, fake social posts, or fake quotations as evidence.

## Voice and audio

```bash
ace voice prepare last
ace voice generate last
ace voice status last
ace voice test --output /tmp/ace-voice-test.wav
```

The default Fatah example uses Kokoro `af_sarah`. ACE prepares a dedicated spoken script, normalizes narration loudness, applies gentle compression and peak protection, and may mix licensed account music according to the selected mood.

## Publishing safety

Publishing is intentionally disabled by default and always approval-gated:

```bash
ace publish prepare last
ace publish approve last
ace publish schedule last "2026-08-01T18:00:00+01:00"
ace publish status last
```

These commands create a publishing plan. They do not post to social platforms in v2.0.1.

## Diagnostics and repair

```bash
ace check --offline
ace check --live
ace quota status
ace status last
ace fix last
ace edit inspect last
```

Run the built-in tests:

```bash
ace test quick
ace test render
ace test full --report
ace release verify --report
```

`ace test full` creates a temporary account and generation, builds evidence, produces adaptive captions, creates text-light original visuals, synthesizes test narration, renders a real 1080×1920 MP4 with FFmpeg, checks black/silent output, and validates `COMPLETE_WITH_WARNINGS` logic.

## Persistent data layout

```text
~/.config/ace/
├── config.json
├── secrets.env
├── active-account
└── accounts/<slug>/account.yaml

~/.local/share/ace/
├── accounts/<slug>/assets/
└── content/<slug>/<platform>/<type>/<generation>/

~/.cache/ace/
├── cache.sqlite3
└── provider-state.json
```

Each generation contains structured research, evidence, claims, visuals, captions, licenses, audio, editing plans, reports, and exports.

## Honest boundaries

- Live cloud, stock, social, and browser-provider calls require connectivity, valid user-owned credentials, quota, and acceptance of each provider’s terms.
- ACE records source and license metadata but cannot guarantee that every possible use is legally permitted.
- A social reaction may be relevant to a video without being trustworthy evidence.
- Automatic claim verification reduces risk but does not replace human review for breaking, medical, legal, financial, or other high-stakes content.
- AI-generated illustrations must not be presented as photographs or documentary evidence.
- Publishing remains a human-approved future integration.

See `docs/architecture.md`, `docs/commands.md`, `docs/security.md`, and `docs/migration.md` for implementation details.

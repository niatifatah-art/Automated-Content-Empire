# Automated Content Empire — ACE v2.1.0

ACE is a cloud-first, evidence-aware content production system for short-form and long-form social video. It researches, writes, verifies, narrates, directs visuals and captions, builds an editing plan, and renders with FFmpeg.

ACE v2.1 focuses on a practical goal: **the result should feel edited, not merely assembled.**

## Start here — simplified commands

Create a complete YouTube Short:

```bash
ace make "What really happens when you type a URL"
```

Choose the creative direction without remembering the old command tree:

```bash
ace make "Linux mistakes beginners keep making" \
  --look fun \
  --footage broll \
  --humor auto \
  --mode best
```

Review, repair and open the result:

```bash
ace review
ace redo 4
ace open
```

Check the installation:

```bash
ace checkup --offline
ace checkup --live
```

Friendly aliases are intentionally small:

```text
make     create a complete video
review   score the latest result
redo 4   rebuild one weak shot
open     play the finished video
checkup  diagnose the installation
```

The advanced command tree remains supported for inspection and precise repairs. The former flags `--style`, `--media`, `--memes`, `--quality`, and `--reference` remain compatibility aliases for `--look`, `--footage`, `--humor`, `--mode`, and `--ref`.

## v2.1 Creative Editing Engine

### B-Roll Director

ACE no longer repeats one broad stock query for a whole sentence. It produces distinct searches for:

- the literal action
- the important object or screen
- close-up detail
- over-the-shoulder context
- the real environment
- an optional documentary establishing shot

Abstract mechanisms still prioritize explainers or controlled demonstrations. Literal scenes can favor strong account-owned or licensed B-roll with `--footage broll`. `--footage original` disables stock retrieval while retaining original explainers, evidence and typography.

### Meme Director

Memes are now connected to the automatic candidate tournament. ACE creates an original reaction card only when it detects a natural comedy beat and the style permits humor. Serious incidents, evidence and precise data suppress memes automatically.

```bash
--humor auto   # default: only natural, appropriate beats
--humor off    # never use memes
--humor on     # look harder for a genuine punchline; never force one
```

### Editing grammar

Every shot receives an explicit creative directive for motion, transition, overlay, emphasis and source-window selection. The renderer now supports:

- punch-ins, slow pushes and directional pans
- style-aware contrast and finishing
- scene-boundary-aware B-roll trimming
- optional secondary visual overlays
- hard cuts and brief soft entrances instead of repeated fade-to-black dips
- different editing behavior for technical, documentary, gaming, challenge, serious and playful content

### Reference pacing

Use a reference video to borrow its average cut rhythm without copying its content:

```bash
ace make "Your topic" --ref ~/Videos/reference.mp4
```

ACE analyzes orientation, cut count and average shot duration, then uses those timing hints when grouping narration into visual beats.

### Creative quality report

`ace review` now reports:

- real B-roll coverage from stock/account footage
- dynamic visual coverage from demos, explainers and footage
- static-card ratio
- repeated-format runs
- motion and transition variety
- meme count versus the selected style budget
- average shot duration

This report warns when a video resembles a slideshow even if the technical render is valid.

### Better Gemini quota handling

ACE distinguishes a short rate limit from a per-day Gemini quota. A daily quota places only that credential/model route into a reset-length cooldown, allows other configured cloud routes to continue, and displays a concise error instead of the complete provider JSON.

The friendly quality modes also control cloud request budgets:

```text
quick      deterministic visual planning; minimum cloud calls
balanced   one targeted cloud intent refinement; no routine frame judge
best       targeted cloud refinement and judging for the most important shots
```

ACE does not spend a cloud request on every subtitle chunk. It groups narration into visual beats and reserves cloud judgment for the shots where it can change the result.

## Visual Intelligence foundation retained

ACE still uses structured `ShotIntent`, `VisualCandidate`, `VisualScore` and `VisualDecision` records. Official evidence, browser/terminal demonstrations, original explainers, generated concepts, article/social cards, account assets, licensed stock, memes, typography and minimal screens can all compete. Every selection retains source, license, score, reason, fingerprints and replacement history.

Useful advanced inspection commands:

```bash
ace visuals explain last --shot 4
ace visuals candidates last --shot 4
ace visuals regenerate last --shot 4
ace visuals replace last --shot 4 --candidate CANDIDATE_ID
ace state show last
```

## Honest scope

ACE v2.1 is an automated creative editor, not a replacement for a full nonlinear editor. High-quality live B-roll depends on the available provider inventory and on actual frame-level matches; `best` mode stops rather than quietly accepting a low creative score. It does not claim human-level motion tracking, hand-crafted compositing or guaranteed viral performance. Cloud frame judging, live resource search and official-page capture require configured credentials and network access. The deterministic route remains usable offline and fails safely when an external service is unavailable.

## Install on Linux Mint / Ubuntu

System tools:

```bash
sudo apt update
sudo apt install -y python3-venv ffmpeg libsndfile1 espeak-ng fonts-dejavu-core
```

Create a clean environment:

```bash
unzip Automated-Content-Empire-2.1.0.zip
cd Automated-Content-Empire-2.1.0

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
cd Automated-Content-Empire-2.1.0
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

These commands create approval records and a publishing plan. ACE v2.1 does not post directly to social platforms.

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
.

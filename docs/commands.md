# ACE command map

## The five commands most people need

```bash
ace make "What happens when you type a URL"
ace review
ace redo 4
ace open
ace checkup --live
```

### `ace make`

Creates the research, script, narration, visual plan, editing package and final video.

```bash
ace make "Linux mistakes beginners keep making" \
  --look fun \
  --footage mixed \
  --humor auto \
  --mode balanced
```

Friendly controls:

```text
--look     adaptive | tech | clean | hype | challenge | serious | fun
--footage  mixed | original | broll
--humor    auto | off | on
--mode     quick | balanced | best
--ref      optional reference video for cut rhythm
```

Quality modes are also cloud-request budgets. `quick` is mostly deterministic, `balanced` uses targeted refinement, and `best` judges only the most important shots rather than calling the cloud for every caption.

Compatibility aliases remain valid:

```text
--style     = --look
--media     = --footage
--memes     = --humor
--quality   = --mode
--reference = --ref
```

### `ace review`

Shows one concise report covering technical status, visual relevance, captions, editing, live/B-roll coverage, static-card ratio, meme budget and the final path.

```bash
ace review
ace review --json
```

### `ace redo`

Repairs one weak shot without rebuilding research, script and narration.

```bash
ace redo 4
ace redo 4 --look serious
```

Run without a shot number to rebuild the complete visual/edit route:

```bash
ace redo
```

### `ace open`

Opens the final video:

```bash
ace open
ace open --preview
```

### `ace checkup`

Checks installation and configured services:

```bash
ace checkup --offline
ace checkup --live
```

## Advanced creation

```text
ace create PLATFORM TYPE TOPIC [--auto|--assisted|--manual] [--package|--render|--both]
ace youtube TYPE TOPIC ...
ace tiktok TYPE TOPIC ...
ace instagram TYPE TOPIC ...
ace facebook TYPE TOPIC ...
ace x TYPE TOPIC ...
ace linkedin TYPE TOPIC ...
```

## Setup and identity

```text
ace init [--upgrade|--force]
ace new
ace account list|show|use|edit|check|upgrade
ace settings [--edit]
ace config show|path|get|set
ace secrets path|edit|status
```

## Models and resilience

```text
ace models routes
ace models search QUERY
ace models use TASK ALIAS
ace models test PROVIDER MODEL [--allow-degraded]
ace models ready
ace credentials status|test
ace quota status|providers
```

## Research and evidence

```text
ace research collect|verify|show [GENERATION]
ace sources add URL [GENERATION]
ace sources add-post URL [GENERATION]
ace sources list [GENERATION]
ace sources inspect URL
ace evidence build|list [GENERATION]
ace evidence capture URL [GENERATION] [--approve]
```

## Visual resources and intelligence

```text
ace resources find [GENERATION] --query QUERY --type video|image [--download]
ace resources list [GENERATION]
ace assets add PATH [--tags TAGS]
ace assets list
ace visuals plan|collect|show|inspect [GENERATION]
ace visuals explain [GENERATION] [--shot N]
ace visuals candidates [GENERATION] --shot N
ace visuals regenerate [GENERATION] --shot N [--no-cloud-judge] [--static]
ace visuals replace [GENERATION] --shot N --candidate ID [--approve]
ace visuals approve [GENERATION] --shot N
ace visuals benchmark [--fixtures PATH]
ace images generate [GENERATION] PROMPT [--provider ...] [--model ...]
ace memes search QUERY
ace memes generate [GENERATION] --setup TEXT --punchline TEXT
ace memes fit TOPIC [--mood MOOD]
```

## Captions, voice and editing

```text
ace captions plan|inspect|preview [GENERATION]
ace voice prepare|generate|status [GENERATION]
ace voice test [--output PATH]
ace edit styles
ace edit style set NAME
ace edit package|render|preview|inspect|rerender [GENERATION]
ace edit captions preview [GENERATION]
```

## Restart, repair and state

```text
ace rerun [GENERATION] --from visual-plan|captions|editing|render
ace state show [GENERATION]
ace state events [GENERATION] --limit 100
ace status [GENERATION]
ace fix [GENERATION]
ace recent [--open]
```

## Testing and publishing plans

```text
ace test quick|render|full
ace release verify
ace publish prepare|approve|status [GENERATION]
ace publish schedule [GENERATION] WHEN
```

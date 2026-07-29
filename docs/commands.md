# Command map

## Setup and identity

```text
ace init [--upgrade|--force]
ace new
ace account list|show|use|edit|check
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

## Creation

```text
ace create PLATFORM TYPE TOPIC [--auto|--assisted|--manual] [--package|--render|--both]
ace youtube TYPE TOPIC ...
ace tiktok TYPE TOPIC ...
ace instagram TYPE TOPIC ...
ace facebook TYPE TOPIC ...
ace x TYPE TOPIC ...
ace linkedin TYPE TOPIC ...
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

## Visual resources

```text
ace resources find [GENERATION] --query QUERY --type video|image [--download]
ace resources list [GENERATION]
ace assets add PATH [--tags TAGS]
ace assets list
ace visuals plan|collect|show|inspect [GENERATION]
ace images generate [GENERATION] PROMPT [--provider ...] [--model ...]
ace memes search QUERY
ace memes generate [GENERATION] --setup TEXT --punchline TEXT
ace memes fit TOPIC [--mood MOOD]
```

## Captions, voice, and editing

```text
ace captions plan|inspect|preview [GENERATION]
ace voice prepare|generate|status [GENERATION]
ace voice test [--output PATH]
ace edit styles
ace edit style set NAME
ace edit package|render|preview|inspect|rerender [GENERATION]
ace edit captions preview [GENERATION]
```

## Completion, repair, and publishing

```text
ace check [--offline|--live]
ace status [GENERATION]
ace fix [GENERATION]
ace recent [--open]
ace publish prepare|approve|status [GENERATION]
ace publish schedule [GENERATION] WHEN
ace test quick|render|full
ace release verify
ace guide [TOPIC]
```

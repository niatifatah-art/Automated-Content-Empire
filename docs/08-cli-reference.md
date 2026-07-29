# CLI reference

## Creator commands

```text
ace
ace new
ace create
ace guide
ace check
ace status
ace fix
ace recent
ace account
ace models
ace voice
ace assets
ace settings
```

Use nested help instead of memorizing everything:

```bash
ace create --help
ace account build --help
ace models search --help
ace voice audition --help
ace resources find --help
ace edit render --help
```

## Creation modes

```bash
ace create youtube short "Topic" --manual
ace create youtube short "Topic" --assisted
ace create youtube short "Topic" --auto
ace create youtube short "Topic" --auto --free-only
ace plan youtube short "Topic"
```

Generate independently for every eligible account:

```bash
ace create youtube short "Topic" -A
ace -A
```

## Advanced compatibility

```bash
ace advanced
ace config
ace provider
ace model
ace ai
ace content
ace project
ace workflow
```

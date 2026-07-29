# Troubleshooting

Start with:

```bash
ace check
ace status last
ace fix last
ace guide
```

## Model not found

```bash
ollama list
ace models installed
ace models recommend
ace models use script local-balanced
```

## Voice mismatch or missing narration

```bash
ace voice status
ace voice providers
ace voice audition --provider kokoro -eng
ace voice prepare last
ace voice generate last
```

## No visuals

```bash
ace resources find last
ace resources list last
ace assets add /real/path/to/file.mp4 --tags topic
ace fix last
```

References from news or ordinary websites are not automatically publishable. ACE uses only account-owned or compatible reusable media. The renderer can produce a branded text-motion fallback when no external asset is suitable.

## Black or silent video

v1.7 rejects a final render that is almost entirely black or that lacks expected narration. Review `quality/media-report.json` and run `ace status last`.

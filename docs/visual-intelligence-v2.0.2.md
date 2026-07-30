# ACE v2.0.2 — Visual Intelligence

ACE now asks: **what is the clearest truthful visual language for this exact idea?** It no longer asks only which stock clip matches a few keywords.

## Pipeline

```text
Narration segment
→ deterministic Shot Intent Planner
→ optional cloud refinement
→ candidate-format routing
→ original explainers, evidence, demos, account assets and stock candidates
→ deterministic scoring
→ optional Gemini frame judge
→ stored decision and explanation
→ final validation
```

## Stored artifacts

```text
visuals/
├── shot-intents.json
├── shot-plan.json
├── decisions.json
├── candidates/
│   ├── shot-001.json
│   └── shot-001-scores.json
└── generated/
    ├── explainers/
    └── typography/

quality/
└── visual-intelligence-report.json

state/
└── generation.sqlite3
```

## Repair commands

```bash
ace visuals inspect last
ace visuals explain last
ace visuals explain last --shot 4
ace visuals candidates last --shot 4
ace visuals regenerate last --shot 4
ace visuals replace last --shot 4 --candidate CANDIDATE_ID
ace visuals approve last --shot 4
ace rerun last --from visual-plan
ace rerun last --from captions
ace rerun last --from render
```

## Benchmark

```bash
ace visuals benchmark
```

The gold set covers public Wi-Fi, passkeys, official company news, Linux commands, programming logic, GPU comparisons, serious breaches, and creator challenges.

## Default acceptance thresholds

```yaml
minimum_relevance: 78
minimum_clarity: 72
minimum_vertical_fit: 70
minimum_truthfulness: 95
maximum_duplicate_risk: 25
minimum_average_relevance: 78
maximum_generic_filler_ratio: 0.10
```

Evidence visuals require exact provenance. Simulated, placeholder and reference-only assets never become publishable simply because a model likes their appearance.

# ACE v2.0.2 — Visual Intelligence

## Objective

Replace broad stock-media matching with a visual decision system that selects the clearest format for each narrated idea.

ACE must decide whether a shot is best represented by official evidence, a UI demonstration, an original explainer, a generated concept visual, a chart, a social/article card, a meme, account-owned footage, strong literal stock footage, or intentional typography.

Pexels and Pixabay remain useful providers, but they are no longer the default visual strategy.

## Core pipeline

```text
Narration segment
→ Shot Intent Planner
→ Candidate Format Router
→ Candidate generators/providers
→ Visual Candidate Tournament
→ Multimodal Visual Judge
→ Selected visual with explanation
→ Renderer
→ Final visual validation
```

## Milestone 1 — Benchmark and contracts

Before changing rendering behavior, create a repeatable benchmark and strict data contracts.

### Reference topics

1. Public Wi-Fi security
2. Passkeys
3. Nvidia company partnership announcement
4. Linux command tutorial
5. Python programming mistake
6. Gaming GPU announcement
7. Serious cybersecurity incident
8. Funny technology story
9. Product comparison
10. Seven-day technology challenge

### Required contracts

- `ShotIntent`
- `VisualCandidate`
- `VisualScore`
- `VisualDecision`
- `VisualValidationReport`

Every selected visual must record:

- exact narration segment
- purpose and subject
- preferred and rejected formats
- required and forbidden elements
- source/origin and license state
- candidate scores
- final selection reason
- replacement history

## Shot intent example

```json
{
  "shot_id": "shot-004",
  "narration": "If the network lacks encryption, other people on it may see exposed traffic.",
  "purpose": "explain_mechanism",
  "subject": "unencrypted_network_traffic",
  "mood": "serious_technical",
  "importance": 0.91,
  "preferred_formats": [
    "animated_explainer",
    "browser_demo"
  ],
  "required_elements": [
    "shared_access_point",
    "multiple_devices",
    "data_packets",
    "missing_encryption_lock"
  ],
  "forbidden_elements": [
    "financial_chart",
    "generic_office_interview",
    "abstract_ai_network"
  ],
  "caption_strategy": "short_phrase"
}
```

## Visual formats

1. `official_evidence`
2. `browser_demo`
3. `terminal_demo`
4. `application_demo`
5. `animated_explainer`
6. `generated_concept_image`
7. `article_card`
8. `social_post_card`
9. `data_chart`
10. `comparison_graphic`
11. `timeline`
12. `meme`
13. `account_asset`
14. `stock_video`
15. `stock_image`
16. `kinetic_typography`
17. `minimal_screen`

## Candidate scoring

Each candidate is scored independently for:

- semantic relevance
- clarity in under three seconds
- required-element coverage
- forbidden-element violations
- truthfulness
- vertical suitability
- visual quality
- style match
- text/logo/watermark risk
- duplicate risk
- license/provenance confidence
- generation cost and latency

Initial acceptance thresholds:

```yaml
minimum_relevance: 78
minimum_clarity: 72
minimum_vertical_fit: 70
minimum_truthfulness: 95
maximum_duplicate_risk: 25
```

Evidence visuals require truthfulness `100`.

## Original Explainer Engine

Build reusable motion components for:

- routers and connected devices
- data packets and encryption locks
- authentication flows
- API requests and cloud/local routing
- company partnerships
- timelines and comparisons
- software architecture
- progress and challenge counters
- code execution
- charts and maps

Explain the concept rather than merely decorating the narration.

## Repair workflow

The user must be able to repair a weak shot without regenerating the script or narration.

Planned commands:

```bash
ace visuals inspect last
ace visuals explain last
ace visuals candidates last --shot 4
ace visuals replace last --shot 4
ace visuals regenerate last --shot 4
ace visuals approve last --shot 4
ace rerun last --from visual-plan
ace rerender last
```

## Acceptance criteria

- caption overflow: `0`
- missing visuals: `0`
- black frames: `0`
- broken audio: `0`
- exact duplicate shots: `0`
- placeholder assets in final video: `0`
- unexplained visual decisions: `0`
- generic filler shots: at most `10%`
- average cloud-judge visual relevance: at least `78/100`
- average human benchmark relevance: at least `80/100`

### Public Wi-Fi regression requirements

- no fire footage merely because narration says “burning through data”
- no financial charts
- no generic office interview
- shared-network concepts use diagrams or demonstrations
- rogue hotspot uses a fake-network visual
- HTTPS uses a browser/security visual
- cellular hotspot uses a real phone-hotspot visual

## Engineering influences

Ideas are adapted independently after license review; code is not merged blindly.

- Video-Automation-Creation: typed stages, word timing, ASS and FFmpeg patterns
- youtube-automation-agent: persistent state and real/generated/placeholder safety
- n8n-nodes-openai-litellm: provider metadata and trace events
- AI-Content-Studio: approvals, stage restart, style propagation
- Llemonstack: future plugin manifests and capability registry
- MoneyPrinterV2: future publishing preflight and retry patterns
- self-hosted-ai-starter-kit: future optional deployment profiles
- youtube-shorts-pipeline: OCR and deduplication concepts only

## Development order

1. benchmark fixtures
2. typed visual contracts
3. deterministic rule-based intent baseline
4. cloud Shot Intent Planner
5. candidate-format router
6. Original Explainer Engine v1
7. visual candidate scoring
8. multimodal cloud judge
9. per-shot repair commands
10. public-Wi-Fi regression rerender
11. full benchmark evaluation
12. release review

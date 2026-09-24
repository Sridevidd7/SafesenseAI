# Phase 5 — ML-Assisted Semantic Layer

## What it does

Phase 5 adds a lightweight, reproducible ML layer that improves *semantic
understanding* of safety reports — matching paraphrased text to canonical safety
concepts and providing a semantic similarity signal — while the existing
deterministic safety intelligence remains the **only** authority for safety
decisions.

What it provides:

- **Semantic candidates**: confidence-scored matches from report text to a
  curated bank of canonical safety concepts (8 life-saving rules + 8 canonical
  barrier failures, names mirroring `rule_classifier` / `barrier_dictionary`).
- **Deterministic validation of every candidate**: an ML suggestion only becomes
  "accepted" when the authoritative deterministic engines independently support
  it; otherwise it is explicitly "rejected" with the validator's evidence.
- **Hybrid similarity** (`hybrid_report_similarity`): deterministic report
  similarity (`pattern_engine.compute_similarity`) combined with an ML semantic
  cosine for pattern intelligence use.

What it never does:

- It does **not** modify risk scores, risk thresholds, SIF classification,
  temporal safety states, barrier determination, rule classification, exposure
  state, or any final safety severity decision.
- It is not a training pipeline and does not claim dataset-wide accuracy.

## Architecture / data flow

```
Raw report
   ↓
Existing deterministic NLP            (risk_engine, rule_classifier,
   ↓                                   barrier_dictionary, concept_extractor)
ML-assisted semantic layer            (services/semantic_service.py — advisory)
   ↓
Normalized semantic representation    (candidates + confidence + source text)
   ↓
Existing deterministic validation     (validate_candidate → accepted/rejected)
   ↓
Risk / SIF / safety decisions         (unchanged deterministic engines)
```

The ML layer can never become `Raw report → ML → final safety decision`:
`validate_candidate()` gates every candidate, and no safety engine consumes ML
output as input.

## Model / dependencies

| Item | Value |
|---|---|
| Model id | `sklearn-tfidf-word12-semantic-concepts-v1` |
| Technique | TF-IDF (word 1–2 grams, sublinear TF, L2 norm) + cosine similarity over a curated concept bank |
| Library | scikit-learn **1.3.2** (already a core dependency — no new packages) |
| Training data | None. The vectorizer is fitted lazily, deterministically, in-process from the static concept bank in `semantic_service.py` |
| Artifacts | None downloaded or bundled. No network access at runtime |
| Reproducibility | Fixed bank + fixed vectorizer params ⇒ identical vocabulary/IDF on every run and machine |

Why not sentence-transformers/transformers: torch is broken in the current
environment (DLL load failure), the packages are not in `requirements.txt`,
and model files would add hundreds of MB. The TF-IDF bank achieves the Phase 5
goal (paraphrase-level candidate generation with deterministic validation) at
negligible cost. Revisiting with a proper embedding model is a future option
behind the same service interface.

## Semantic representation

Each candidate (`SemanticCandidate.to_dict()`) carries:

- `canonical_concept`, `concept_type` (`life_saving_rule` | `barrier_failure`)
- `confidence` — TF-IDF cosine similarity in `[0, 1]`. This expresses textual
  semantic relatedness only; **it is not proof of a safety violation**.
- `runner_up_concept`, `runner_up_confidence`, `margin`, `ambiguous` —
  ranking context; `ambiguous=True` when top-2 confidences are within
  `AMBIGUITY_MARGIN` (0.05).
- `status` — `suggested` → `accepted`/`rejected` after validation.
- `source_text` — the (PII-sanitized at API boundary) text that produced it.
- `validation` — `{validator, accepted, evidence}` with the deterministic
  engine's independent verdict (e.g. detected barriers, rule scores).

## Confidence handling

| Parameter | Default | Meaning |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | 0.20 | Candidates below this cosine similarity are not surfaced |
| `AMBIGUITY_MARGIN` | 0.05 | Top-1 vs top-2 gap below which the match is flagged ambiguous |

Confidence is never compared against safety thresholds and never gates any
safety behavior — it only controls what the advisory layer surfaces.

## Deterministic validation

- `life_saving_rule` candidates are accepted only if
  `rule_classifier.classify_life_saving_rule` returns the same rule as primary
  **or** gives it a weighted score ≥ 3.
- `barrier_failure` candidates are accepted only if
  `barrier_dictionary.detect_barriers` detects the same canonical barrier
  (exact name or conservative token-Jaccard name affinity ≥ 0.75).
- Unknown concept types are always rejected.

## Fallback behavior

- `SAFESENSE_SEMANTIC_ML=off` (env var) disables the ML layer entirely;
  every entry point then returns `available=false` and empty candidates.
- If model build or inference fails, the same degradation applies with a
  `degraded_reason`; nothing raises into the safety pipeline.
- `hybrid_report_similarity` returns the unchanged deterministic similarity
  (model: `deterministic_fallback`) when the semantic component is unavailable.
- Pattern adapter integration degrades to `semantic_signal=None`; pattern
  intelligence is unaffected.

## API surface (advisory, PII-sanitized)

- `POST /api/semantic/analyze` — validated candidates for text (min 5 chars).
- `GET  /api/semantic/model-info` — provenance, availability, thresholds,
  safety-boundary statement.

## Integration points (all additive)

- `services/semantic_service.py` — the entire ML layer (self-contained).
- `services/pattern_adapter.py` — optional `semantic_signal` on patterns.
- `routes/semantic.py` + `main.py` router registration.
- `requirements.txt` — comments only (no new packages).

## Tests & benchmark

```bash
cd backend
pytest test_semantic_service.py     # 28 tests: paraphrases, thresholds, validation, fallback, determinism, safety regression
pytest test_semantic_benchmark.py   # deterministic benchmark suite (fixed corpus)
pytest test_semantic_api.py         # API + PII + degraded-mode tests
pytest                              # full regression suite
```

Benchmark (fixed corpus of representative safety examples — **no generalized
accuracy claim**): recall@3 = 10/10, top-1 precision = 8/10, validation
agreement = 9/10, negative cases (non-safety text) produce zero accepted
safety concepts. The benchmark deliberately includes a case where ML suggests a
plausible barrier paraphrase that deterministic validation rejects
("machine serviced while still connected to power"), demonstrating the safety gate.

## Limitations

- TF-IDF semantics are lexical-statistical: genuinely novel phrasings with zero
  token overlap with the bank may not surface (mitigated by the paraphrase-rich
  bank descriptions and by the deterministic engines, which remain authoritative).
- The concept bank is curated and small (16 concepts). Extending it means adding
  `ConceptSpec` entries; barrier names must match `barrier_dictionary` exactly
  (enforced by a test).
- Confidence values are corpus-specific; the benchmark thresholds apply to the
  fixed benchmark corpus only.
- `top-1` on rule-vs-barrier co-occurring texts may return the more specific
  barrier concept rather than the rule — by design; both appear in top-k.

## Out of scope (unchanged)

PostgreSQL/vector DB migration, production deployment, dashboard redesign,
custom supervised model training, cloud LLM dependencies — Phase 6/7 territory.

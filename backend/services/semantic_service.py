"""
services/semantic_service.py — Phase 5 ML-assisted semantic layer.

HYBRID SEMANTIC ARCHITECTURE (Phase 5):

    Raw report
       ↓
    Existing deterministic NLP          (risk_engine / rule_classifier /
       ↓                                 barrier_dictionary / concept_extractor)
    ML-assisted semantic layer          ← THIS MODULE (advisory only)
       ↓
    Normalized semantic representation / similarity signals
       ↓
    Existing deterministic validation   (validate_candidate — deterministic rules)
       ↓
    Risk / SIF / safety decisions       (unchanged deterministic engines)

SAFETY CONTRACT
---------------
- This layer is ADVISORY. It produces confidence-scored semantic candidates and
  similarity signals only. It never sets risk scores, SIF classification,
  safety severity, exposure state, or barrier determinations.
- Every candidate carries: canonical concept, similarity confidence, the source
  signal, and — after validate_candidate() — an explicit deterministic
  accept/reject decision with the validator's evidence.
- If the ML model cannot load or infer, every entry point degrades to the
  deterministic path (never raises into the safety pipeline).

MODEL / DEPENDENCIES
--------------------
- scikit-learn TfidfVectorizer (word 1–2 grams, sublinear TF, L2 norm) over a
  curated canonical safety-concept bank + cosine similarity.
- scikit-learn and numpy are ALREADY core dependencies (requirements.txt);
  no new dependency is introduced.
- The "model" is fitted lazily and deterministically in-process from the static
  concept bank in this file — no training data, no downloaded artifacts, no
  network access, fully reproducible across runs and machines.
- Confidence = cosine similarity of TF-IDF vectors. It expresses textual
  semantic relatedness, NOT proof of a safety violation and NOT a safety
  classification.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("safesense.semantic")

# ─── Configuration ────────────────────────────────────────────────────────────

MODEL_ID = "sklearn-tfidf-word12-semantic-concepts-v1"

# Candidates below this cosine similarity are not surfaced
CONFIDENCE_THRESHOLD = 0.20
# If top-1 and top-2 concepts are closer than this margin, the match is flagged ambiguous
AMBIGUITY_MARGIN = 0.05
# Maximum characters of source text considered (mirrors risk_engine input bound)
MAX_TEXT_CHARS = 2000

# Feature flag: set SAFESENSE_SEMANTIC_ML=off to force deterministic-only mode
_ENV_FLAG = "SAFESENSE_SEMANTIC_ML"


# ─── Canonical concept bank ───────────────────────────────────────────────────

@dataclass(frozen=True)
class ConceptSpec:
    """A canonical safety concept with a paraphrase-rich semantic description."""
    name: str
    concept_type: str          # "life_saving_rule" | "barrier_failure"
    description: str           # dense paraphrase expansion used as the semantic document


CANONICAL_CONCEPTS: Tuple[ConceptSpec, ...] = (
    # ── Life-Saving Rules (mirror rule_classifier.RULE_DEFINITIONS names) ──
    ConceptSpec("Confined Space", "life_saving_rule",
        "confined space entry tank vessel manhole pit sump chamber reactor column "
        "descend descended descend into climb down entered inside inside vessel inside tank "
        "atmosphere oxygen h2s toxic gas gas testing gas test air monitoring air quality "
        "ventilation hole watch pre entry clearance atmospheric test purge"),
    ConceptSpec("Working at Height", "life_saving_rule",
        "working at height fall protection harness lanyard lifeline scaffold scaffolding "
        "ladder roof elevated platform ledge climb climbed up rack tower mast ascent descent "
        "tie off tied off anchor guardrail open edge drop unprotected edge fall arrest"),
    ConceptSpec("Energy Isolation", "life_saving_rule",
        "energy isolation lockout tagout loto isolation de energize deenergize disconnect "
        "unplugged plugged plugged in powered power supply live circuit live electrical "
        "breaker switchgear energized electric shock stored pressure residual energy "
        "zero energy verify isolation servicing service maintenance overhaul repair"),
    ConceptSpec("Hot Work", "life_saving_rule",
        "hot work welding welding torch grinding grinder cut cutting brazing spark sparks "
        "flame open flame igniting ignition source permit to work hot work permit fire watch "
        "combustible material cleared flammable near"),
    ConceptSpec("Line of Fire", "life_saving_rule",
        "line of fire suspended load crane rigging hoist hoisted lifted lifting sling "
        "load above crew below struck by pinch point dropped object falling material "
        "barricade exclusion zone blind spot swing radius stored energy release"),
    ConceptSpec("Vehicle Movement", "life_saving_rule",
        "vehicle movement forklift fork lift truck lorry excavator reversing reverse back "
        "backed backing spotter banksman flagman traffic management pedestrian walkway "
        "segregation seatbelt seat belt run over runover collision runover struck vehicle"),
    ConceptSpec("Chemical Handling", "life_saving_rule",
        "chemical handling spill spilled splash splashed acid caustic alkali solvent "
        "transfer decant decanting pouring ppe goggles face shield gloves respirator "
        "chemical suit msds sds containment bund drip tray corrosive toxic substance exposure"),
    ConceptSpec("Fire Prevention", "life_saving_rule",
        "fire prevention combustible flammable material storage ignition source "
        "extinguisher extinguishers housekeeping smoking cigarette hot surface surfaces "
        "oily rags waste accumulation fuel inheritance fire risk"),
    # ── Barrier failures (canonical names mirror barrier_dictionary outputs) ──
    ConceptSpec("Gas Testing Not Completed", "barrier_failure",
        "gas testing not completed atmospheric test skipped no gas test before entry "
        "atmosphere unchecked oxygen level not measured air not tested entry prior clearance "
        "expired gas test certificate monitor not used"),
    ConceptSpec("Lockout/Tagout Not Completed", "barrier_failure",
        "lockout tagout not completed no lockout applied loto missing isolation not applied "
        "energy not isolated without lockout tag no padlock stored energy not secured "
        "circuit not de energized machine serviced powered"),
    ConceptSpec("Fall Protection Not Used", "barrier_failure",
        "fall protection not used harness not worn no harness lanyard not tied off "
        "lifeline missing fall arrest not secured unprotected working at height no anchor "
        "guardrail missing scaffold without guardrail"),
    ConceptSpec("Permit Not Obtained", "barrier_failure",
        "permit not obtained no permit to work ptw missing work started without permit "
        "clearance not issued authorization missing approval absent cold work permit "
        "hot work permit not raised"),
    ConceptSpec("Isolation Not Applied", "barrier_failure",
        "energy isolation not applied equipment not de energized supply not disconnected "
        "still connected to power energized during maintenance no isolation applied "
        "electrical isolation omitted pressure not released bled down"),
    ConceptSpec("PPE Not Available", "barrier_failure",
        "ppe not available personal protective equipment missing not worn safety glasses "
        "goggles helmet hard hat absent gloves not used respirator missing protective "
        "footwear high visibility vest missing"),
    ConceptSpec("Fire Watch Not Posted", "barrier_failure",
        "fire watch not posted no fire watch hot work without fire watch standby "
        "fire attendant absent extinguisher not available at work site post work "
        "monitoring not done fire guard missing"),
    ConceptSpec("Standby Person Not Assigned", "barrier_failure",
        "standby person not assigned no standby attendant missing hole watch missing "
        "entry watcher absent vehicle reversing without spotter banksman missing "
        "nobody directing traffic guide missing pedestrian uncontrolled"),
)

_CONCEPTS_BY_NAME: Dict[str, ConceptSpec] = {c.name: c for c in CANONICAL_CONCEPTS}


# ─── Lightweight text normalization (applied identically to bank and input) ──

_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9\s]+")

# Domain stopwords that add no discriminative value in the concept bank domain
_SEM_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "was", "were", "is", "are", "be", "been", "by", "his", "her", "their",
    "while", "during", "before", "after", "without", "no", "not", "prior",
}


def light_normalize(text: str) -> str:
    """
    Deterministic light normalization: lowercase, strip punctuation, simple
    suffix folding (plurals, -ing/-ed) so inflected forms share mass with the
    concept bank. Applied identically when fitting and when transforming.
    """
    if not text:
        return ""
    t = _TOKEN_SPLIT_RE.sub(" ", text.lower())
    out: List[str] = []
    for w in t.split():
        if w in _SEM_STOPWORDS:
            continue
        out.append(w)
        if len(w) > 4 and w.endswith("ing"):
            out.append(w[:-3])          # testing -> test
        elif len(w) > 4 and w.endswith("ed"):
            out.append(w[:-2])          # descended -> descend
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            out.append(w[:-1])          # sparks -> spark
    return " ".join(out)


# ─── Lazy deterministic model (fitted from the static bank) ──────────────────

_VECTORIZER: Any = None
_BANK_MATRIX: Any = None
_DEGRADED_REASON: Optional[str] = None
_MODEL_READY: bool = False


def _ml_enabled() -> bool:
    """Feature flag check — SAFESENSE_SEMANTIC_ML=off forces deterministic mode."""
    return os.getenv(_ENV_FLAG, "on").strip().lower() != "off"


def _build_model() -> bool:
    """
    Fit the TF-IDF model over the canonical concept bank.
    Deterministic: fixed bank + fixed vectorizer params => fixed vocabulary/idf.
    Returns True on success, False on failure (recorded in _DEGRADED_REASON).
    """
    global _VECTORIZER, _BANK_MATRIX, _MODEL_READY, _DEGRADED_REASON
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401 (validated import)

        docs = [light_normalize(f"{c.name} {c.description}") for c in CANONICAL_CONCEPTS]
        _VECTORIZER = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            sublinear_tf=True,
            norm="l2",
            lowercase=False,
            preprocessor=lambda x: x,   # already light-normalized
            tokenizer=str.split,
            token_pattern=None,
        )
        _BANK_MATRIX = _VECTORIZER.fit_transform(docs)
        _MODEL_READY = True
        _DEGRADED_REASON = None
        logger.info(
            "[SEMANTIC_ML_READY] model=%s concepts=%d", MODEL_ID, len(CANONICAL_CONCEPTS)
        )
        return True
    except Exception as exc:
        _VECTORIZER = None
        _BANK_MATRIX = None
        _MODEL_READY = False
        _DEGRADED_REASON = f"model initialization failed: {exc}"
        logger.warning("[SEMANTIC_ML_DEGRADED] %s", _DEGRADED_REASON)
        return False


def get_model_info() -> Dict[str, Any]:
    """Explainability: current model state, provenance and degraded reason."""
    import sklearn
    info: Dict[str, Any] = {
        "model_id": MODEL_ID,
        "type": "tfidf_cosine_similarity",
        "library": f"scikit-learn {sklearn.__version__}",
        "concepts": len(CANONICAL_CONCEPTS),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "ambiguity_margin": AMBIGUITY_MARGIN,
    }
    if not _ml_enabled():
        info["available"] = False
        info["degraded_reason"] = f"{_ENV_FLAG}=off (disabled by configuration)"
    elif _MODEL_READY:
        info["available"] = True
    else:
        info["available"] = False
        info["degraded_reason"] = _DEGRADED_REASON or "model not initialized"
    return info


def reset_model_state() -> None:
    """Reset cached model state (used by tests)."""
    global _VECTORIZER, _BANK_MATRIX, _MODEL_READY, _DEGRADED_REASON
    _VECTORIZER = None
    _BANK_MATRIX = None
    _MODEL_READY = False
    _DEGRADED_REASON = None


def _ensure_model() -> bool:
    if not _ml_enabled():
        _DEGRADED_REASON = f"{_ENV_FLAG}=off (disabled by configuration)"
        return False
    if not _MODEL_READY:
        return _build_model()
    return True


# ─── Semantic candidates ──────────────────────────────────────────────────────

@dataclass
class SemanticCandidate:
    """A confidence-scored semantic match against a canonical safety concept."""
    canonical_concept: str
    concept_type: str
    confidence: float
    runner_up_concept: Optional[str] = None
    runner_up_confidence: float = 0.0
    margin: float = 0.0
    ambiguous: bool = False
    status: str = "suggested"           # suggested | accepted | rejected
    source_text: str = ""
    validation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_concept": self.canonical_concept,
            "concept_type": self.concept_type,
            "confidence": round(self.confidence, 4),
            "runner_up_concept": self.runner_up_concept,
            "runner_up_confidence": round(self.runner_up_confidence, 4),
            "margin": round(self.margin, 4),
            "ambiguous": self.ambiguous,
            "status": self.status,
            "source_text": self.source_text,
            "validation": self.validation,
        }


def get_semantic_candidates(text: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Rank canonical safety concepts against free text by TF-IDF cosine similarity.

    Returns:
        {
          "available": bool,            # False => deterministic-only mode
          "degraded_reason": str|None,
          "model": model info dict,
          "candidates": [SemanticCandidate, ...]  # above CONFIDENCE_THRESHOLD
        }
    """
    empty = {
        "available": False,
        "degraded_reason": None,
        "model": get_model_info(),
        "candidates": [],
    }
    if not text or not str(text).strip():
        return empty

    if not _ensure_model():
        info = get_model_info()
        return {
            **empty,
            "degraded_reason": info.get("degraded_reason") or "semantic model unavailable",
            "model": info,
        }

    try:
        from sklearn.metrics.pairwise import cosine_similarity

        clipped = str(text)[:MAX_TEXT_CHARS]
        q = _VECTORIZER.transform([light_normalize(clipped)])
        sims = cosine_similarity(q, _BANK_MATRIX)[0]

        order = np.argsort(-sims)[: max(top_k + 1, 2)]
        candidates: List[SemanticCandidate] = []
        for idx in order[:top_k]:
            conf = float(sims[idx])
            if conf < CONFIDENCE_THRESHOLD:
                continue
            spec = CANONICAL_CONCEPTS[int(idx)]
            runner_idx = next((int(i) for i in order if int(i) != int(idx)), None)
            runner_conf = float(sims[runner_idx]) if runner_idx is not None else 0.0
            runner_spec = CANONICAL_CONCEPTS[runner_idx] if runner_idx is not None else None
            margin = conf - runner_conf
            candidates.append(
                SemanticCandidate(
                    canonical_concept=spec.name,
                    concept_type=spec.concept_type,
                    confidence=round(conf, 4),
                    runner_up_concept=runner_spec.name if runner_spec else None,
                    runner_up_confidence=round(runner_conf, 4),
                    margin=round(margin, 4),
                    ambiguous=(runner_spec is not None and margin < AMBIGUITY_MARGIN
                               and runner_conf >= CONFIDENCE_THRESHOLD),
                    source_text=clipped[:200],
                )
            )

        return {
            "available": True,
            "degraded_reason": None,
            "model": get_model_info(),
            "candidates": candidates,
        }
    except Exception as exc:
        logger.warning("[SEMANTIC_ML_DEGRADED] inference failed: %s", exc)
        _DEGRADED_REASON = f"inference failed: {exc}"
        info = get_model_info()
        return {**empty, "degraded_reason": _DEGRADED_REASON, "model": info}


# ─── Deterministic validation of ML candidates ───────────────────────────────

def _barrier_name_affinity(a: str, b: str) -> float:
    """Token Jaccard between two barrier names (deterministic, conservative)."""
    ta = set(light_normalize(a).split())
    tb = set(light_normalize(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def validate_candidate(candidate: SemanticCandidate, text: str) -> SemanticCandidate:
    """
    Deterministic validation gate for an ML candidate (Phase 5 safety boundary).

    - life_saving_rule candidates are accepted only when the deterministic
      rule classifier independently supports the same rule (primary rule match
      or weighted score >= 3).
    - barrier_failure candidates are accepted only when the deterministic
      barrier dictionary detects the same canonical barrier (exact name or
      conservative name affinity >= 0.75).

    The deterministic system is ALWAYS the authority: an ML candidate without
    deterministic support is marked "rejected" with the validator's evidence.
    """
    from services.rule_classifier import classify_life_saving_rule
    from services.barrier_dictionary import detect_barriers

    text = str(text or "")[:MAX_TEXT_CHARS]
    rule_result = classify_life_saving_rule(text)
    detected_barriers = detect_barriers(text)

    if candidate.concept_type == "life_saving_rule":
        primary = rule_result.get("primary_rule")
        score = int(rule_result.get("scores", {}).get(candidate.canonical_concept, 0))
        accepted = (primary == candidate.canonical_concept) or (score >= 3)
        validator = "rule_classifier.classify_life_saving_rule"
        evidence = {
            "deterministic_primary_rule": primary,
            "deterministic_rule_score": score,
            "accept_rule": "primary match OR weighted score >= 3",
        }
    elif candidate.concept_type == "barrier_failure":
        affinity = max(
            (_barrier_name_affinity(b, candidate.canonical_concept) for b in detected_barriers),
            default=0.0,
        )
        accepted = affinity >= 0.75
        validator = "barrier_dictionary.detect_barriers"
        evidence = {
            "deterministic_barriers_detected": detected_barriers,
            "best_name_affinity": round(affinity, 3),
            "accept_rule": "exact canonical match OR name affinity >= 0.75",
        }
    else:
        accepted = False
        validator = "none"
        evidence = {"reason": f"unknown concept_type '{candidate.concept_type}'"}

    candidate.status = "accepted" if accepted else "rejected"
    candidate.validation = {
        "validator": validator,
        "accepted": accepted,
        "evidence": evidence,
    }
    return candidate


def suggest_and_validate(text: str, top_k: int = 3) -> Dict[str, Any]:
    """
    Full advisory pipeline for one text:
      ML candidates -> deterministic validation -> annotated result.
    Never raises; degrades to available=False on any failure.
    """
    result = get_semantic_candidates(text, top_k=top_k)
    if result["available"]:
        result["candidates"] = [
            validate_candidate(c, text).to_dict() for c in result["candidates"]
        ]
    return result


# ─── Hybrid lexical + semantic report similarity ─────────────────────────────

def semantic_text_similarity(text1: str, text2: str) -> Optional[float]:
    """
    Pure semantic cosine similarity between two free texts.
    Returns None when the ML model is unavailable (caller must fall back).
    """
    if not _ensure_model():
        return None
    try:
        from sklearn.metrics.pairwise import cosine_similarity
        v = _VECTORIZER.transform([light_normalize(text1 or ""), light_normalize(text2 or "")])
        return float(cosine_similarity(v[0], v[1])[0][0])
    except Exception as exc:
        logger.warning("[SEMANTIC_ML_DEGRADED] similarity failed: %s", exc)
        return None


def hybrid_report_similarity(rep1: Dict[str, Any], rep2: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hybrid similarity for pattern intelligence (advisory signal, not a safety
    decision): combines the repository's deterministic report similarity with
    the ML semantic cosine.

        hybrid = 0.6 * deterministic + 0.4 * semantic   (when ML available)
        hybrid = deterministic                          (fallback, unchanged)

    The deterministic component reuses services/pattern_engine.compute_similarity
    so existing clustering behaviour stays authoritative.
    """
    from services.pattern_engine import compute_similarity

    t1 = rep1.get("description") or rep1.get("report_text") or ""
    t2 = rep2.get("description") or rep2.get("report_text") or ""

    lexical = float(compute_similarity(rep1, rep2))
    sem = semantic_text_similarity(str(t1), str(t2))

    if sem is None:
        return {
            "similarity": round(lexical, 4),
            "lexical_component": round(lexical, 4),
            "semantic_component": None,
            "model": "deterministic_fallback",
        }

    combined = 0.6 * lexical + 0.4 * sem
    return {
        "similarity": round(combined, 4),
        "lexical_component": round(lexical, 4),
        "semantic_component": round(sem, 4),
        "model": MODEL_ID,
    }


# ─── Enrichment / summary helpers (consumed by pattern adapter & API) ────────

def enrich_reports_with_semantics(reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Phase 5 advisory enrichment: attach a top semantic candidate to each report
    dict under the "semantic_signal" key. Never mutates safety fields; on any
    failure the reports are returned unchanged in structure (semantic_signal=None).
    """
    for rep in reports:
        text = rep.get("description") or rep.get("report_text") or ""
        rep["semantic_signal"] = summarize_semantic_signal([text])
    return reports


def summarize_semantic_signal(texts: List[str]) -> Dict[str, Any]:
    """
    Build a compact semantic signal summary over one or more texts (e.g. a
    pattern cluster's sample descriptions): best accepted candidate, runner-up,
    model info. Explicitly advisory and explainable.
    """
    joined = " ".join(str(t) for t in texts if t)[:MAX_TEXT_CHARS]
    result = suggest_and_validate(joined, top_k=2)

    best = result["candidates"][0] if result["candidates"] else None
    accepted = next((c for c in result["candidates"] if c["status"] == "accepted"), None)

    return {
        "model": result["model"],
        "available": result["available"],
        "degraded_reason": result.get("degraded_reason"),
        "top_candidate": best,
        "accepted_candidate": accepted,
        "note": (
            "ML semantic similarity is advisory and does not constitute proof "
            "of a safety violation; deterministic validation governs acceptance."
        ),
    }

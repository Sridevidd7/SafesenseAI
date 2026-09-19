import os
import json
import re
from groq import Groq
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)
load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY")) if os.getenv("GROQ_API_KEY") else None



from hashlib import md5

try:
    from services.llm_logger import log_llm_event
except ImportError:
    try:
        from backend.services.llm_logger import log_llm_event
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from llm_logger import log_llm_event

FORBIDDEN_GENERIC_TERMS = [
    "hazardous environment",
    "dangerous conditions",
    "unsafe situation",
    "high-risk scenario",
    "severe consequences"
]

GENERIC_ONLY_VERBS = {"fix", "ensure", "handle", "manage", "check", "do"}

CACHE = {}


def get_cache_key(report_data: dict) -> str:
    raw = json.dumps(report_data, sort_keys=True, default=str)
    return md5(raw.encode()).hexdigest()


def fallback_response(report_data: dict, reason: str = "fallback_default", model_used: str = "none") -> dict:
    barriers = report_data.get("barrier_failures") or [report_data.get("barrier_failure", "None")]
    if isinstance(barriers, str):
        barriers = [barriers]
    barrier_str = ", ".join(barriers)
    rule = report_data.get("life_saving_rule") or report_data.get("category") or "General Safety"
    level = report_data.get("risk_level", "LOW")
    score = report_data.get("risk_score", 0)
    sif = report_data.get("sif_potential", "NO")

    return {
        "root_cause": f"{rule} violation due to {barrier_str}.",
        "risk_explanation": f"Evaluated as {level} risk ({score}/100) based strictly on detected barrier failure(s) [{barrier_str}] and SIF potential '{sif}'.",
        "potential_consequence": f"Hazard exposure associated with unmitigated {rule} conditions.",
        "recommended_actions": [
            f"Stop any active work violating {rule} immediately.",
            f"Apply mandatory safety controls for {barrier_str}.",
            f"Obtain formal supervisor verification under {rule} before proceeding."
        ],
        "source": "fallback_rule_based",
        "explanation_source": "fallback_rule_based",
        "validation_passed": False,
        "validation_reason": reason,
        "model_used": model_used,
        "cached": False
    }


def validate_llm_output(parsed: dict, report_data: dict, return_reason: bool = True):
    """
    Validates that LLM output adheres to strict structural grounding:
    Returns (is_valid: bool, reason: str) if return_reason=True, else is_valid.
    """
    def make_res(valid: bool, reason: str):
        if return_reason:
            return valid, reason
        return valid

    if not isinstance(parsed, dict):
        return make_res(False, "schema_invalid")

    # 1. Schema keys & non-empty checks
    required_keys = ["root_cause", "risk_explanation", "potential_consequence", "recommended_actions"]
    if not all(k in parsed for k in required_keys):
        return make_res(False, "schema_invalid")

    if not isinstance(parsed["recommended_actions"], list) or len(parsed["recommended_actions"]) == 0:
        return make_res(False, "schema_invalid")

    for k in ["root_cause", "risk_explanation", "potential_consequence"]:
        if not isinstance(parsed[k], str) or not parsed[k].strip():
            return make_res(False, "schema_invalid")

    root_cause = parsed["root_cause"].strip()
    risk_exp = parsed["risk_explanation"].strip()
    pot_consequence = parsed["potential_consequence"].strip()
    actions = [str(a).strip() for a in parsed["recommended_actions"]]

    # 2. Word Constraints
    if len(root_cause.split()) > 25 or len(risk_exp.split()) > 40 or len(pot_consequence.split()) > 25:
        return make_res(False, "word_limit_exceeded")

    # 3. Forbidden Generic Terms Filter
    all_text_combined = f"{root_cause} {risk_exp} {pot_consequence} {' '.join(actions)}".lower()
    for forbidden in FORBIDDEN_GENERIC_TERMS:
        if forbidden.lower() in all_text_combined:
            return make_res(False, "forbidden_term_detected")

    # 4. Life-Saving Rule Enforcement (in root_cause OR in at least one recommended action)
    rule = report_data.get("life_saving_rule") or report_data.get("category")
    rule_clean = str(rule).strip() if rule else ""
    if rule_clean and rule_clean.lower() not in ["general safety", "none", "unknown", ""]:
        rule_pattern = rf"\b{re.escape(rule_clean)}\b"
        in_rc = bool(re.search(rule_pattern, root_cause, re.IGNORECASE))
        in_actions = any(bool(re.search(rule_pattern, act, re.IGNORECASE)) for act in actions)
        if not (in_rc or in_actions):
            return make_res(False, "rule_missing")

    # 5. Exact Barrier Token Matching (STRICT full phrase match in root_cause or risk_explanation)
    barriers = report_data.get("barrier_failures")
    if not barriers and report_data.get("barrier_failure"):
        barriers = [report_data.get("barrier_failure")]

    clean_barriers = []
    if barriers:
        if isinstance(barriers, str):
            barriers = [barriers]

        for barrier in barriers:
            b_clean = str(barrier).strip()
            if b_clean and b_clean.lower() not in ["none", "unknown", ""]:
                clean_barriers.append(b_clean)
                b_pattern = rf"\b{re.escape(b_clean)}\b"
                in_rc = bool(re.search(b_pattern, root_cause, re.IGNORECASE))
                in_re = bool(re.search(b_pattern, risk_exp, re.IGNORECASE))
                if not (in_rc or in_re):
                    return make_res(False, "missing_barrier_match")

    # 6. Recommended Actions Quality Enforcement
    if len(actions) != 3:
        return make_res(False, "actions_count_invalid")

    # Check at least ONE action explicitly mentions Life-Saving Rule or barrier
    has_any_rule = any((rule_clean.lower() in a.lower()) for a in actions) if rule_clean else True
    has_any_barrier = any(any(b.lower() in a.lower() for b in clean_barriers) for a in actions) if clean_barriers else True

    if not (has_any_rule or has_any_barrier):
        return make_res(False, "generic_action")

    for action in actions:
        words = action.split()
        if len(words) < 4:
            return make_res(False, "generic_action")

        # Check if action only consists of generic filler words
        non_stop_words = [w.strip(".,;:!?").lower() for w in words]
        if all(w in GENERIC_ONLY_VERBS or len(w) <= 3 for w in non_stop_words):
            return make_res(False, "generic_action")


    # 7. Risk Level Consistency
    input_level = str(report_data.get("risk_level", "LOW")).upper()
    combined_exp_upper = f"{root_cause} {risk_exp}".upper()
    all_levels = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    conflicting_levels = all_levels - {input_level}

    # Verify input risk level is present in root_cause or risk_explanation
    if input_level not in combined_exp_upper:
        return make_res(False, "risk_level_mismatch")

    # Verify no conflicting level is asserted
    for conf_lvl in conflicting_levels:
        patterns = [
            rf"\bIS {conf_lvl}\b",
            rf"\bRATED AS {conf_lvl}\b",
            rf"\bLEVEL:\s*{conf_lvl}\b",
            rf"\bLEVEL IS {conf_lvl}\b",
            rf"\bCLASSIFIED AS {conf_lvl}\b"
        ]
        for pat in patterns:
            if re.search(pat, combined_exp_upper):
                return make_res(False, "risk_level_mismatch")


    return make_res(True, "passed")


async def generate_llm_explanation(report_data: dict) -> dict:
    desc = report_data.get("description") or report_data.get("report_text", "")
    rule = report_data.get("life_saving_rule") or report_data.get("category", "General Safety")
    barriers = report_data.get("barrier_failures") or [report_data.get("barrier_failure", "Unknown")]
    barrier_list = barriers if isinstance(barriers, list) else [str(barriers)]
    score = report_data.get("risk_score", 0)
    level = report_data.get("risk_level", "LOW")
    sif = report_data.get("sif_potential", "NO")
    confidence = report_data.get("confidence", 0.8)

    # 1. Caching check
    cache_key = get_cache_key(report_data)
    if cache_key in CACHE:
        cached_result = dict(CACHE[cache_key])
        cached_result["cached"] = True
        return cached_result

    used_model = "none"
    try:
        api_key = os.getenv("GROQ_API_KEY")
        groq_client = Groq(api_key=api_key) if api_key else client
        if not groq_client:
            fb = fallback_response(report_data, reason="client_unavailable", model_used="none")
            log_llm_event({
                "description": desc,
                "barriers": barrier_list,
                "risk_level": level,
                "model": "none",
                "validation_passed": False,
                "validation_reason": "client_unavailable",
                "source": "fallback"
            })
            return fb

        candidate_models = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama3-8b-8192"]

        system_instruction = (
            "You are a STRICT industrial safety reasoning engine operating under a ZERO-HALLUCINATION policy.\n"
            "Follow all core execution rules strictly.\n"
            "Output STRICT JSON ONLY. Do NOT explain rules. Do NOT output anything except JSON."
        )

        user_prompt = f"""========================
CORE EXECUTION RULES
========================

1. USE ONLY PROVIDED DATA
- You are given:
  - description
  - life_saving_rule
  - barrier_failures (exact strings)
  - risk_score
  - risk_level
  - sif_potential
  - confidence
- DO NOT introduce:
  - new hazards
  - chemicals
  - machinery
  - injuries not directly implied
  - external assumptions

2. EXACT BARRIER ENFORCEMENT & ROOT CAUSE (CRITICAL)
- Formulate `root_cause` following: "{rule} violation due to {', '.join(barrier_list)} during entry/activity." (or "{rule} violation prevented due to..." if stopped)
- EVERY barrier in `barrier_failures` MUST appear EXACTLY (verbatim) in:
  - root_cause OR risk_explanation
- NO synonyms allowed
- NO rephrasing allowed

3. LIFE-SAVING RULE ENFORCEMENT
- The `life_saving_rule` MUST appear explicitly in:
  - root_cause OR at least one recommended_action

4. SAFE vs VIOLATION LOGIC (MANDATORY)
- If description shows STOP / PREVENTION:
  → classify as PREVENTED condition (NOT violation)
- If action occurred WITHOUT barrier:
  → classify as VIOLATION
- If unclear:
  → reflect uncertainty explicitly (do NOT assume)

5. FACTUAL CONSEQUENCES ONLY (NO SPECULATION)
- Do NOT invent unmentioned specific gases, toxic poisons, or asphyxiation storytelling
- Describe the direct factual hazard condition: e.g. "Worker exposed to unverified atmospheric conditions inside the tank during entry."

6. FORBIDDEN LANGUAGE (AUTO-REJECT IF USED)
DO NOT use:
- "hazardous environment"
- "dangerous conditions"
- "unsafe situation"
- "high-risk scenario"
- "severe consequences"

7. STRICT WORD LIMITS
- root_cause ≤ 25 words
- risk_explanation ≤ 40 words
- potential_consequence ≤ 25 words

8. RISK CONSISTENCY (NON-NEGOTIABLE)
- `risk_explanation` MUST explicitly state the risk level "{level}" and score "{score}/100" (e.g., "CRITICAL risk (95/100) because...")
- DO NOT mention any other risk level

9. RECOMMENDED ACTIONS (NATURAL EXACT-STRING FORMAT)
- EXACTLY 3 actions
- Phrase clearly around resolving barriers (e.g., "Ensure [Barrier Failure] is resolved/completed before...", "Enforce [Life-Saving Rule] by...")
- NO awkward grammar like "Complete [Barrier]"
- NO vague actions like:
  - "follow safety protocols"
  - "ensure safety"

10. LANGUAGE STYLE
- Deterministic
- Technical
- No storytelling
- No exaggeration

========================
OUTPUT FORMAT (STRICT JSON ONLY)
========================

{{
  "root_cause": "...",
  "risk_explanation": "...",
  "potential_consequence": "...",
  "recommended_actions": ["...", "...", "..."]
}}

========================
INPUT DATA
========================

Description: {desc}
Life-Saving Rule: {rule}
Barrier Failures: {', '.join(barrier_list)}
Risk Score: {score}/100 ({level})
SIF Potential: {sif}
Confidence: {confidence}

========================
FINAL INSTRUCTION
========================

- If ANY rule cannot be satisfied → produce best possible compliant output
- DO NOT explain rules
- DO NOT output anything except JSON"""





        response = None
        for model_name in candidate_models:
            try:
                response = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.1
                )
                if response and response.choices:
                    used_model = model_name
                    break
            except Exception:
                continue

        if not response or not response.choices:
            fb = fallback_response(report_data, reason="llm_generation_failed", model_used=used_model)
            log_llm_event({
                "description": desc,
                "barriers": barrier_list,
                "risk_level": level,
                "model": used_model,
                "validation_passed": False,
                "validation_reason": "llm_generation_failed",
                "source": "fallback"
            })
            return fb

        output = response.choices[0].message.content.strip()

        # Clean markdown code fences if model wrapped output
        if output.startswith("```"):
            output = re.sub(r"^```(?:json)?\s*", "", output)
            output = re.sub(r"\s*```$", "", output)

        parsed = json.loads(output)

        # Strict Structural Validation Layer
        is_valid, reason = validate_llm_output(parsed, report_data, return_reason=True)

        # Log LLM call event
        log_llm_event({
            "description": desc,
            "barriers": barrier_list,
            "risk_level": level,
            "model": used_model,
            "validation_passed": is_valid,
            "validation_reason": reason,
            "source": "llm" if is_valid else "fallback"
        })

        if not is_valid:
            return fallback_response(report_data, reason=reason, model_used=used_model)

        parsed["source"] = "llm_verified"
        parsed["explanation_source"] = "llm_verified"
        parsed["validation_passed"] = True
        parsed["validation_reason"] = "passed"
        parsed["model_used"] = used_model
        parsed["cached"] = False

        # Store in cache
        CACHE[cache_key] = dict(parsed)

        return parsed

    except Exception as e:
        fb = fallback_response(report_data, reason=f"exception: {str(e)}", model_used=used_model)
        log_llm_event({
            "description": desc,
            "barriers": barrier_list,
            "risk_level": level,
            "model": used_model,
            "validation_passed": False,
            "validation_reason": f"exception: {str(e)}",
            "source": "fallback"
        })
        return fb





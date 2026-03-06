import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState

ICD_RE = re.compile(r"\b[A-TV-Z][0-9][0-9AB](?:\.[0-9A-TV-Z]{1,4})?\b")


def _to_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _extract_dx_codes(values: List[str]) -> set[str]:
    codes: set[str] = set()
    for item in values:
        for code in ICD_RE.findall(str(item or "")):
            codes.add(code.upper())
    return codes


def _fact_list(facts: Dict[str, Any], key: str) -> List[str]:
    value = facts.get(key)
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return []


def _score_procedure(meta: Dict[str, Any], content: str, facts: Dict[str, Any], dx_codes: set[str]) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0

    flags = facts.get("procedure_flags", {}) if isinstance(facts.get("procedure_flags"), dict) else {}
    documented = " ".join(_fact_list(facts, "documented_procedures")).lower()
    sites = " ".join(_fact_list(facts, "sites")).lower()
    content_lower = content.lower()

    if flags.get("biopsy_performed") and any(k in content_lower for k in ["biopsy", "tangential", "shave"]):
        score += 4
        reasons.append("biopsy flag aligns")
    if flags.get("mohs_performed") and "mohs" in content_lower:
        score += 4
        reasons.append("mohs flag aligns")

    if documented and any(tok in content_lower for tok in documented.split()[:12]):
        score += 2
        reasons.append("matches documented procedure text")

    if sites and any(tok in content_lower for tok in sites.split()[:8]):
        score += 1
        reasons.append("site overlap")

    for code in dx_codes:
        if code in content.upper():
            score += 1
            reasons.append("dx overlap")
            break

    return score, reasons


def _score_enm(meta: Dict[str, Any], content: str, facts: Dict[str, Any]) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0

    patient_type = _to_text(facts.get("patient_type"))
    visit_type = _to_text(facts.get("visit_type"))
    place_of_service = _to_text(facts.get("place_of_service"))

    enm_type = _to_text(meta.get("enmType"))
    facility_code = str(meta.get("facilityCode") or "").strip()

    if patient_type == "established" and enm_type == "estpat":
        score += 4
        reasons.append("patient_type established")
    elif patient_type == "new" and enm_type == "newpat":
        score += 4
        reasons.append("patient_type new")

    if visit_type == "followup" and enm_type == "estpat":
        score += 2
        reasons.append("followup visit match")

    if place_of_service == "office" and facility_code == "11":
        score += 1
        reasons.append("office POS match")

    if enm_type == "other":
        score -= 2
        reasons.append("deprioritize generic other")

    if "office visit" in content.lower():
        score += 1
        reasons.append("office visit family")

    return score, reasons


def _score_modifier(meta: Dict[str, Any], content: str, facts: Dict[str, Any]) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0

    modifier = str(meta.get("modifier") or "").strip().upper()
    laterality = {str(v).lower() for v in _fact_list(facts, "laterality")}

    score += 1
    reasons.append("active modifier")

    if "left" in laterality and modifier == "LT":
        score += 2
        reasons.append("laterality left")
    if "right" in laterality and modifier == "RT":
        score += 2
        reasons.append("laterality right")

    if bool(meta.get("enmModifier")):
        score += 1
        reasons.append("eligible for E/M")

    if "distinct procedural service" in content.lower():
        score += 1
        reasons.append("distinct procedure option")

    return score, reasons


def _candidate_item(category: str, code: str, meta: Dict[str, Any], content: str, score: int, reasons: List[str]) -> Dict[str, Any]:
    desc_key = "codeDesc" if category == "procedure" else "enmCodeDesc"
    desc = str(meta.get(desc_key) or "").strip()
    return {
        "category": category,
        "code": code,
        "description": desc,
        "score": score,
        "reasons": reasons,
        "metadata": meta,
        "content_excerpt": " ".join((content or "").split())[:280],
    }


def _top_ranked(items: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:k]


async def candidate_selection_node(state: BillingState) -> BillingState:
    retrieval = state.get("retrieval", [])
    facts = state.get("encounter_facts", {}) if isinstance(state.get("encounter_facts"), dict) else {}
    dx_codes = _extract_dx_codes(_fact_list(facts, "documented_dx_codes"))

    procedures: Dict[str, Dict[str, Any]] = {}
    enm: Dict[str, Dict[str, Any]] = {}
    modifiers: Dict[str, Dict[str, Any]] = {}

    reasoning: List[Dict[str, Any]] = []

    for item in retrieval:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {}) or {}
        content = str(item.get("content") or "")
        item_type = str(meta.get("type") or "")

        if item_type == "procedure" and meta.get("proCode") is not None:
            code = str(meta.get("proCode"))
            score, reasons = _score_procedure(meta, content, facts, dx_codes)
            procedures[code] = _candidate_item("procedure", code, meta, content, score, reasons)
            reasoning.append({"category": "procedure", "code": code, "score": score, "reasons": reasons})

        elif item_type == "enm" and meta.get("enmCode") is not None:
            code = str(meta.get("enmCode"))
            score, reasons = _score_enm(meta, content, facts)
            enm[code] = _candidate_item("enm", code, meta, content, score, reasons)
            reasoning.append({"category": "enm", "code": code, "score": score, "reasons": reasons})

        elif item_type == "modifier" and meta.get("modifier") is not None:
            code = str(meta.get("modifier"))
            score, reasons = _score_modifier(meta, content, facts)
            modifiers[code] = _candidate_item("modifier", code, meta, content, score, reasons)
            reasoning.append({"category": "modifier", "code": code, "score": score, "reasons": reasons})

    state["procedure_candidates"] = _top_ranked(list(procedures.values()), k=15)
    state["enm_candidates"] = _top_ranked(list(enm.values()), k=10)
    state["modifier_candidates"] = _top_ranked(list(modifiers.values()), k=20)
    state["candidate_reasoning"] = reasoning
    return state

import sys
from pathlib import Path
from typing import Any, Dict, Iterable

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from src.agent.state_helpers import ICD_RE, _append_narrative


def _empty_facts(notes: Dict[str, Any] | None = None) -> Dict[str, Any]:
    visit = notes.get("visit", {}) if isinstance(notes, dict) else {}
    procedure_flags = (
        notes.get("procedure_flags", {}) if isinstance(notes, dict) else {}
    )
    return {
        "visit_type": "unknown",
        "patient_type": "unknown",
        "place_of_service": visit.get("place_of_service") or "unknown",
        "documented_procedures": [],
        "documented_dx_codes": [],
        "sites": [],
        "laterality": [],
        "closure_type": "unknown",
        "procedure_flags": {
            "biopsy_performed": bool(procedure_flags.get("biopsy_performed", False)),
            "mohs_performed": bool(procedure_flags.get("mohs_performed", False)),
        },
        "evidence_snippets": [],
    }


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_icd_codes(*values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            text = " ".join(_as_text(v) for v in value)
        else:
            text = _as_text(value)
        for code in ICD_RE.findall(text):
            normalized = code.upper()
            if normalized not in seen:
                seen.add(normalized)
                out.append(normalized)
    return out


def _append_unique(items: list[str], values: Iterable[Any]) -> None:
    seen = {item.lower() for item in items}
    for value in values:
        text = _as_text(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(text)


def _snippet(evidence: list[dict[str, str]], field: str, value: Any) -> None:
    text = _as_text(value)
    if not text:
        return
    evidence.append({"field": field, "evidence": text[:200]})


def _infer_visit_type(notes: Dict[str, Any], base: Dict[str, Any]) -> str:
    complaint = _as_text(notes.get("chief_complaint")).lower()
    summary = _as_text(notes.get("raw_patient_summary")).lower()
    assessment = _as_text(notes.get("assessment")).lower()
    procedures = " ".join(base.get("documented_procedures", [])).lower()

    joined = " ".join([complaint, summary, assessment, procedures])
    if any(
        token in joined
        for token in ["follow up", "follow-up", "followup", "return visit"]
    ):
        return "followup"
    if "consult" in joined:
        return "consult"
    if any(token in joined for token in ["new patient", "new pt"]):
        return "new"
    if base["procedure_flags"].get("biopsy_performed") or base["procedure_flags"].get(
        "mohs_performed"
    ):
        return "procedure_only"
    return "unknown"


def _infer_patient_type(notes: Dict[str, Any], visit_type: str) -> str:
    complaint = _as_text(notes.get("chief_complaint")).lower()
    summary = _as_text(notes.get("raw_patient_summary")).lower()
    joined = f"{complaint} {summary}"
    if "new patient" in joined or visit_type == "new":
        return "new"
    if any(
        token in joined for token in ["follow up", "follow-up", "followup", "return"]
    ):
        return "established"
    return "unknown"


def _infer_closure_type(biopsy: Dict[str, Any], mohs: Dict[str, Any]) -> str:
    details = []
    if isinstance(biopsy.get("biopsy"), dict):
        details.extend(biopsy["biopsy"].get("details", []))
    if isinstance(mohs.get("mohs"), dict):
        details.extend(mohs["mohs"].get("details", []))

    for item in details:
        if not isinstance(item, dict):
            continue
        hint = _as_text(item.get("closure_hint")).lower()
        if hint in {"complex", "intermediate", "layered", "simple"}:
            return hint
        if item.get("int_suture") and item.get("ext_suture"):
            return "layered"
    return "unknown"


async def note_fact_extractor_node(state: BillingState) -> BillingState:
    notes = state.get("notes", {}) if isinstance(state.get("notes"), dict) else {}
    biopsy = state.get("biopsy", {}) if isinstance(state.get("biopsy"), dict) else {}
    mohs = state.get("mohs", {}) if isinstance(state.get("mohs"), dict) else {}
    general = state.get("general", {}) if isinstance(state.get("general"), dict) else {}

    base = _empty_facts(notes)
    evidence: list[dict[str, str]] = []

    diagnoses = notes.get("diagnoses")
    procedures = notes.get("procedures_documented")
    base["documented_dx_codes"] = _extract_icd_codes(diagnoses)
    _append_unique(base["documented_procedures"], [procedures])

    biopsy_details = (
        biopsy.get("biopsy", {}).get("details", [])
        if isinstance(biopsy.get("biopsy"), dict)
        else []
    )
    mohs_details = (
        mohs.get("mohs", {}).get("details", [])
        if isinstance(mohs.get("mohs"), dict)
        else []
    )

    # Include general procedure names so the LLM sees them as documented
    general_details = (
        general.get("general", []) if isinstance(general.get("general"), list) else []
    )

    for detail in [*biopsy_details, *mohs_details]:
        if not isinstance(detail, dict):
            continue
        _append_unique(
            base["documented_procedures"],
            [detail.get("procedure_name"), detail.get("technique")],
        )
        _append_unique(base["sites"], [detail.get("site")])
        _append_unique(
            base["laterality"], [detail.get("laterality"), detail.get("location")]
        )

    for detail in general_details:
        if not isinstance(detail, dict):
            continue
        _append_unique(
            base["documented_procedures"],
            [detail.get("procedure_name"), detail.get("technique")],
        )
        _append_unique(base["sites"], [detail.get("site")])
        _append_unique(base["laterality"], [detail.get("location")])

    normalized_laterality: list[str] = []
    for item in base["laterality"]:
        low = item.lower()
        if "left" in low:
            normalized_laterality.append("left")
        elif "right" in low:
            normalized_laterality.append("right")
        elif "bilat" in low:
            normalized_laterality.append("bilateral")
    base["laterality"] = sorted(set(normalized_laterality))

    base["visit_type"] = _infer_visit_type(notes, base)
    base["patient_type"] = _infer_patient_type(notes, base["visit_type"])
    base["closure_type"] = _infer_closure_type(biopsy, mohs)

    _snippet(evidence, "chief_complaint", notes.get("chief_complaint"))
    _snippet(evidence, "diagnoses", diagnoses)
    _snippet(evidence, "procedures_documented", procedures)
    if biopsy_details:
        _snippet(evidence, "biopsy", biopsy_details[0])
    if mohs_details:
        _snippet(evidence, "mohs", mohs_details[0])
    if general_details:
        _snippet(evidence, "general", general_details[0])
    base["evidence_snippets"] = evidence

    state["encounter_facts"] = base
    _append_narrative(
        state,
        (
            "fact_extractor_node: "
            f"visit_type={base.get('visit_type')} patient_type={base.get('patient_type')} "
            f"sites={len(base.get('sites', []))} procedures={len(base.get('documented_procedures', []))}"
        ),
    )
    return state

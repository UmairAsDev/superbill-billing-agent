import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from services.llm_factory import get_openai_llm
from src.services.prompts import fact_extractor_prompt


CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|```$", re.IGNORECASE)


def _empty_facts(notes: Dict[str, Any] | None = None) -> Dict[str, Any]:
    visit = notes.get("visit", {}) if isinstance(notes, dict) else {}
    procedure_flags = notes.get("procedure_flags", {}) if isinstance(notes, dict) else {}
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


def _parse_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = CODE_FENCE_RE.sub("", text).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


async def note_fact_extractor_node(state: BillingState) -> BillingState:
    llm = get_openai_llm()
    chain = fact_extractor_prompt | llm

    notes = state.get("notes", {})

    response = await chain.ainvoke(
        {
            "patient": notes.get("patient"),
            "visit": notes.get("visit"),
            "chief_complaint": notes.get("chief_complaint"),
            "patient_summary": notes.get("raw_patient_summary"),
            "history": notes.get("history"),
            "exam": notes.get("exam"),
            "assessment": notes.get("assessment"),
            "diagnoses": notes.get("diagnoses"),
            "procedures": notes.get("procedures_documented"),
            "biopsy": state.get("biopsy", {}),
            "mohs": state.get("mohs", {}),
        }
    )

    parsed = _parse_json(str(response.content))
    base = _empty_facts(notes if isinstance(notes, dict) else None)
    base.update({k: v for k, v in parsed.items() if v is not None})

    state["encounter_facts"] = base
    return state

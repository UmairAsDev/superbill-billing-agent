
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from services.llm_factory import get_openai_llm
from config.schema import BillingState
from config.config import settings
from src.services.prompts import billing_prompt


def _format_retrieval_rules(state: BillingState) -> str:
    retrieval = state.get("retrieval", [])
    if not isinstance(retrieval, list) or not retrieval:
        return "(none)"

    lines: list[str] = []
    for item in retrieval:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {}) or {}
        content = (item.get("content") or "").strip()
        item_type = str(meta.get("type") or "").strip() or "unknown"

        code: str | None = None
        if item_type == "procedure" and meta.get("proCode") is not None:
            code = str(meta.get("proCode"))
        elif item_type == "enm" and meta.get("enmCode") is not None:
            code = str(meta.get("enmCode"))
        elif item_type == "modifier" and meta.get("modifier") is not None:
            code = str(meta.get("modifier"))

        prefix = f"[{item_type}]" + (f" {code}" if code else "")
        if content:
            # Keep it compact to avoid blowing up the prompt.
            compact = " ".join(content.split())
            lines.append(f"{prefix}: {compact}")
        else:
            lines.append(f"{prefix}: (no content)")

    return "\n".join(lines) if lines else "(none)"


def _build_medication_context(state: BillingState) -> dict:
    prescriptions = state.get("prescriptions", {})
    if not isinstance(prescriptions, dict):
        return {}

    # Do not pass previous superbill rows to the LLM to avoid answer leakage.
    return {
        "prescription": prescriptions.get("prescription", []),
        "previous_medications": prescriptions.get("previous_medications", []),
    }


def _format_candidates(items: object, category: str) -> str:
    if not isinstance(items, list) or not items:
        return f"[{category}] (none)"

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        desc = str(item.get("description") or "").strip()
        score = item.get("score", 0)
        reasons = item.get("reasons", [])
        reason_text = ", ".join(str(r) for r in reasons[:3]) if isinstance(reasons, list) else ""
        lines.append(f"[{category}] {code} | score={score} | {desc} | reasons: {reason_text}")

    return "\n".join(lines) if lines else f"[{category}] (none)"


async def billing_llm_node(state: BillingState) -> BillingState:
    llm = get_openai_llm()

    chain = billing_prompt | llm

    notes = state.get("notes", {})

    response = await chain.ainvoke(
        {
            "patient": notes.get("patient"),
            "visit": notes.get("visit"),
            "chief_complaint": notes.get("chief_complaint"),
            "patient_summary": notes.get("raw_patient_summary"),
            "history": notes.get("history"),
            "diagnoses": notes.get("diagnoses"),
            "exam": notes.get("exam"),
            "assessment": notes.get("assessment"),
            "procedures": notes.get("procedures_documented"),
            "biopsy": state.get("biopsy", {}),
            "mohs": state.get("mohs", {}),
            "medications": _build_medication_context(state),
            "retrieval_rules": _format_retrieval_rules(state),
            "procedure_candidates": _format_candidates(state.get("procedure_candidates", []), "procedure"),
            "enm_candidates": _format_candidates(state.get("enm_candidates", []), "enm"),
            "modifier_candidates": _format_candidates(state.get("modifier_candidates", []), "modifier"),
            "em_policy": settings.EM_POLICY_TEXT,
        }
    )

    state["billing_context"] = {
        "llm_output": response.content,
    }
    return state







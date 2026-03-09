import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from services.llm_factory import get_openai_llm
from src.services.prompts import self_correction_prompt
from src.agent.state_helpers import _append_narrative
from loguru import logger


CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|```$", re.IGNORECASE)


def _clean_json_text(value: Any) -> str:
    return CODE_FENCE_RE.sub("", str(value or "")).strip()


def _truncate(value: Any, max_len: int = 600) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _normalize_code_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _has_bill_lines(parsed: dict[str, Any]) -> bool:
    cpt_items = _normalize_code_items(
        parsed.get("CPT_codes")
        or parsed.get("cpt_codes")
        or parsed.get("CPT")
        or parsed.get("cpt")
        or parsed.get("procedures")
    )
    em_items = _normalize_code_items(
        parsed.get("E_M_codes")
        or parsed.get("em_codes")
        or parsed.get("E/M")
        or parsed.get("em")
        or parsed.get("evaluation_and_management")
    )
    service_items = _normalize_code_items(
        parsed.get("cpt_services")
        or parsed.get("services")
        or parsed.get("service_lines")
    )
    return bool(cpt_items or em_items or service_items)


def _format_retrieval_rules(state: BillingState) -> str:
    retrieval = state.get("retrieval", [])
    if not isinstance(retrieval, list) or not retrieval:
        return "(none)"

    type_caps = {"procedure": 6, "enm": 4, "modifier": 8}
    emitted = {"procedure": 0, "enm": 0, "modifier": 0}
    lines: list[str] = []
    for item in retrieval:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {}) or {}
        item_type = str(meta.get("type") or "").strip() or "unknown"
        if item_type in type_caps and emitted[item_type] >= type_caps[item_type]:
            continue

        code: str | None = None
        if item_type == "procedure" and meta.get("proCode") is not None:
            code = str(meta.get("proCode"))
        elif item_type == "enm" and meta.get("enmCode") is not None:
            code = str(meta.get("enmCode"))
        elif item_type == "modifier" and meta.get("modifier") is not None:
            code = str(meta.get("modifier"))

        prefix = f"[{item_type}]" + (f" {code}" if code else "")
        desc = str(
            meta.get("codeDesc")
            or meta.get("enmCodeDesc")
            or meta.get("description")
            or ""
        ).strip()
        hint_parts: list[str] = []
        if item_type == "procedure":
            if meta.get("minQty") is not None or meta.get("maxQty") is not None:
                hint_parts.append(f"qty={meta.get('minQty')}-{meta.get('maxQty')}")
            if any(k in meta for k in ("ChargePerUnit", "chargePerUnit")):
                charge_value = meta.get("ChargePerUnit", meta.get("chargePerUnit"))
                hint_parts.append(f"chargePerUnit={charge_value}")
        elif item_type == "modifier":
            hint_parts.append(f"enmModifier={meta.get('enmModifier')}")
        elif item_type == "enm":
            if meta.get("enmType"):
                hint_parts.append(f"enmType={meta.get('enmType')}")
            if meta.get("facilityCode"):
                hint_parts.append(f"facilityCode={meta.get('facilityCode')}")

        hint_text = f" | {'; '.join(str(p) for p in hint_parts if str(p).strip())}" if hint_parts else ""
        lines.append(
            f"{prefix}: { _truncate(desc, max_len=180) if desc else '(no description)' }{hint_text}"
        )
        if item_type in emitted:
            emitted[item_type] += 1

    return "\n".join(lines) if lines else "(none)"


def _format_candidates(items: object, category: str) -> str:
    if not isinstance(items, list) or not items:
        return f"[{category}] (none)"

    lines: list[str] = []
    max_items = {"procedure": 8, "enm": 5, "modifier": 8}.get(category, 6)
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        desc = str(item.get("description") or "").strip()
        score = item.get("score", 0)
        reasons = item.get("reasons", [])
        reason_text = (
            ", ".join(str(r) for r in reasons[:2]) if isinstance(reasons, list) else ""
        )
        lines.append(
            f"[{category}] {code} | score={score} | {_truncate(desc, max_len=120)} | reasons: {_truncate(reason_text, max_len=120)}"
        )

    return "\n".join(lines) if lines else f"[{category}] (none)"


async def self_correction_node(state: BillingState) -> BillingState:
    billing_context = (
        state.get("billing_context", {})
        if isinstance(state.get("billing_context"), dict)
        else {}
    )
    initial_output = (
        billing_context.get("llm_output")
        or billing_context.get("initial_llm_output")
        or "{}"
    )

    # Fast validation mapping to avoid completely unnecessary LLM calls (Cost Optimization)
    needs_correction = False
    try:
        parsed = json.loads(_clean_json_text(initial_output))
        if parsed.get("none_of_the_above") is True:
            needs_correction = True
        elif not _has_bill_lines(parsed):
            needs_correction = True

        # If modifiers are heavily used and it's a multi-procedure visit, review it
        cpt_lines = _normalize_code_items(parsed.get("CPT_codes", []))
        if len(cpt_lines) > 1 and any(
            len(cpt.get("modifiers", [])) > 0 for cpt in cpt_lines
        ):
            needs_correction = True

    except Exception:
        needs_correction = True  # JSON is broken, definitely need correction

    if not needs_correction:
        billing_context["self_corrected_output"] = initial_output
        billing_context["llm_output"] = initial_output
        state["self_correction_notes"] = [
            "Skipped correction LLM pass: Initial outputs passed validation heuristic."
        ]
        state["billing_context"] = billing_context
        _append_narrative(
            state,
            "self_correction_node: initial bill looks clean; skipped redundant second pass to save cost.",
        )
        return state

    llm = get_openai_llm()
    chain = self_correction_prompt | llm

    try:
        response = await chain.ainvoke(
            {
                "narrative_summary": _truncate(
                    state.get("narrative_summary"), max_len=1400
                ),
                "encounter_facts": state.get("encounter_facts"),
                "retrieval_rules": _format_retrieval_rules(state),
                "procedure_candidates": _format_candidates(
                    state.get("procedure_candidates", []), "procedure"
                ),
                "enm_candidates": _format_candidates(
                    state.get("enm_candidates", []), "enm"
                ),
                "modifier_candidates": _format_candidates(
                    state.get("modifier_candidates", []), "modifier"
                ),
                "initial_bill": initial_output,
            }
        )
    except Exception as exc:
        logger.error(f"self_correction_node: LLM call failed: {exc}")
        billing_context["self_corrected_output"] = initial_output
        billing_context["llm_output"] = initial_output
        state["self_correction_notes"] = [
            f"Self-correction LLM call failed ({exc}); retained initial bill draft."
        ]
        state["billing_context"] = billing_context
        _append_narrative(
            state, f"self_correction_node: LLM call failed — {exc}; kept initial draft"
        )
        return state

    raw_output = str(response.content or "")
    parsed_ok = False
    try:
        parsed = json.loads(_clean_json_text(raw_output))
        parsed_ok = isinstance(parsed, dict)
    except json.JSONDecodeError:
        parsed_ok = False

    if parsed_ok and _has_bill_lines(parsed):
        billing_context["self_corrected_output"] = raw_output
        billing_context["llm_output"] = raw_output
        notes_field = (
            parsed.get("self_correction_notes") if isinstance(parsed, dict) else None
        )
        if isinstance(notes_field, list):
            state["self_correction_notes"] = [str(item) for item in notes_field]
        _append_narrative(
            state,
            "self_correction_node: completed second-pass audit and updated bill draft",
        )
    else:
        billing_context["self_corrected_output"] = initial_output
        billing_context["llm_output"] = initial_output
        state["self_correction_notes"] = [
            "Self-correction returned non-billable structure or invalid JSON; retained initial bill draft."
        ]
        _append_narrative(
            state,
            "self_correction_node: non-billable correction output; kept initial draft",
        )

    state["billing_context"] = billing_context
    return state

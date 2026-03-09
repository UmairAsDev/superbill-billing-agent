import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).parent.parent))
from services.llm_factory import get_openai_llm
from config.schema import BillingState
from config.config import settings
from src.services.prompts import billing_prompt
from src.agent.state_helpers import _append_narrative
from loguru import logger


def _truncate(value: Any, max_len: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


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


async def billing_llm_node(state: BillingState) -> BillingState:
    llm = get_openai_llm()
    chain = billing_prompt | llm

    try:
        response = await chain.ainvoke(
            {
                "narrative_summary": _truncate(
                    state.get("narrative_summary"), max_len=1200
                ),
                "encounter_facts": state.get("encounter_facts", {}),
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
                "em_policy": settings.EM_POLICY_TEXT,
            }
        )
    except Exception as exc:
        logger.error(f"billing_llm_node: LLM call failed: {exc}")
        billing_context = (
            state.get("billing_context", {})
            if isinstance(state.get("billing_context"), dict)
            else {}
        )
        billing_context["llm_error"] = str(exc)
        billing_context["llm_output"] = "{}"
        billing_context["initial_llm_output"] = "{}"
        state["billing_context"] = billing_context
        _append_narrative(state, f"billing_llm_node: LLM call failed — {exc}")
        return state

    billing_context = (
        state.get("billing_context", {})
        if isinstance(state.get("billing_context"), dict)
        else {}
    )
    billing_context["initial_llm_output"] = response.content
    billing_context["llm_output"] = response.content
    billing_context["narrative_summary"] = state.get("narrative_summary", "")
    state["billing_context"] = billing_context
    _append_narrative(
        state,
        "billing_llm_node: produced initial bill draft from extracted facts",
    )
    return state

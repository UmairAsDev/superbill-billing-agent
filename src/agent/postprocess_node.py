import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState


CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|```$", re.IGNORECASE)
QTY_MOD_RE = re.compile(r"^x\s*(\d+)$", re.IGNORECASE)


def _parse_llm_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    cleaned = CODE_FENCE_RE.sub("", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


def _index_retrieval(retrieval: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    procedures: Dict[str, Dict[str, Any]] = {}
    enm: Dict[str, Dict[str, Any]] = {}
    modifiers: Dict[str, Dict[str, Any]] = {}

    for item in retrieval:
        if not isinstance(item, dict):
            continue
        meta = item.get("metadata", {})
        item_type = meta.get("type")
        if item_type == "procedure":
            code = str(meta.get("proCode")) if meta.get("proCode") is not None else None
            if code:
                procedures[code] = meta
        elif item_type == "enm":
            code = str(meta.get("enmCode")) if meta.get("enmCode") is not None else None
            if code:
                enm[code] = meta
        elif item_type == "modifier":
            code = str(meta.get("modifier")) if meta.get("modifier") is not None else None
            if code:
                modifiers[code] = meta

    return {"procedures": procedures, "enm": enm, "modifiers": modifiers}


def _normalize_list(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        out: List[str] = []
        for v in value:
            if isinstance(v, dict):
                candidate = (
                    v.get("code")
                    or v.get("modifier")
                    or v.get("icd10")
                    or v.get("icd10_code")
                )
                if candidate is not None and str(candidate).strip():
                    out.append(str(candidate).strip())
                continue
            if str(v).strip():
                out.append(str(v).strip())
        return out
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _normalize_icd10(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        codes: List[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    codes.append(item.strip())
            elif isinstance(item, dict):
                code = item.get("code") or item.get("icd10") or item.get("icd10_code")
                if code is not None and str(code).strip():
                    codes.append(str(code).strip())
        return codes
    if isinstance(value, dict):
        code = value.get("code") or value.get("icd10") or value.get("icd10_code")
        return [str(code).strip()] if code is not None and str(code).strip() else []
    if isinstance(value, str):
        return _normalize_list(value)
    return []


def _get_key(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data[key]
        lower = key.lower()
        for k, v in data.items():
            if k.lower() == lower:
                return v
    return None


def _normalize_code_items(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _candidate_code_set(items: Any) -> set[str]:
    if not isinstance(items, list):
        return set()
    codes: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if code:
            codes.add(code)
    return codes


def _top_candidate_summary(items: Any, limit: int) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "code": str(item.get("code") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "score": item.get("score", 0),
                "reasons": item.get("reasons", []),
            }
        )
    return out


def _normalize_charge_per_unit(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return int(value) == 1
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    return False


def _partition_service_items(
    service_items: List[Dict[str, Any]],
    enm_index: Dict[str, Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cpt_items: List[Dict[str, Any]] = []
    em_items: List[Dict[str, Any]] = []

    for item in service_items:
        code = str(item.get("code") or "").strip()
        if not code:
            continue

        is_em = False
        if code in enm_index:
            is_em = True
        elif code.startswith("99"):
            is_em = True
        else:
            desc = str(item.get("description") or "").lower()
            if "office" in desc and "visit" in desc:
                is_em = True

        if is_em:
            em_items.append(item)
        else:
            cpt_items.append(item)

    return cpt_items, em_items


def _normalize_modifiers(value: Any) -> List[Dict[str, Any]]:
    if not value:
        return []

    def _parse_single(item: Any) -> Dict[str, Any] | None:
        if isinstance(item, str):
            modifier = item.strip()
            return {"modifier": modifier, "applies_to": []} if modifier else None

        if not isinstance(item, dict):
            return None

        modifier_value = (
            item.get("modifier")
            or item.get("mod")
            or item.get("code")
            or item.get("modifier_code")
        )
        if modifier_value is None:
            return None

        applies_to_value = (
            item.get("applies_to")
            or item.get("appliesTo")
            or item.get("cpt")
            or item.get("cpt_code")
            or item.get("target_code")
            or item.get("procedure_code")
        )

        return {
            "modifier": str(modifier_value).strip(),
            "applies_to": _normalize_list(applies_to_value),
        }

    if isinstance(value, str):
        return [
            parsed
            for parsed in (_parse_single(v) for v in _normalize_list(value))
            if parsed and parsed.get("modifier")
        ]

    if isinstance(value, list):
        return [
            parsed
            for parsed in (_parse_single(v) for v in value)
            if parsed and parsed.get("modifier")
        ]

    return []


async def postprocess_billing_node(state: BillingState) -> BillingState:
    billing_context = state.get("billing_context", {})
    llm_output = billing_context.get("llm_output", "")
    parsed = _parse_llm_json(llm_output)

    retrieval = state.get("retrieval", [])
    index = _index_retrieval(retrieval)
    procedure_candidate_codes = _candidate_code_set(state.get("procedure_candidates"))
    enm_candidate_codes = _candidate_code_set(state.get("enm_candidates"))
    modifier_candidate_codes = _candidate_code_set(state.get("modifier_candidates"))
    needs_review = False
    review_reasons: List[str] = []
    dropped_procedure_codes: List[str] = []
    dropped_em_codes: List[str] = []
    dropped_modifiers: List[str] = []

    cpt_items = _normalize_code_items(_get_key(parsed, "CPT_codes", "cpt_codes", "CPT", "cpt", "procedures"))
    em_raw = _get_key(parsed, "E_M_codes", "em_codes", "E/M", "em", "evaluation_and_management")
    em_items = _normalize_code_items(em_raw)
    if not em_items and isinstance(em_raw, dict):
        em_items = [em_raw]

    # Normalize alternate shape fields used by some model responses.
    for item in cpt_items:
        if isinstance(item, dict) and "code" not in item and item.get("cpt"):
            item["code"] = item.get("cpt")
        if isinstance(item, dict) and "linked_icd10" not in item and item.get("linked_diagnosis_icd10"):
            item["linked_icd10"] = item.get("linked_diagnosis_icd10")
    for item in em_items:
        if isinstance(item, dict) and "code" not in item and item.get("cpt"):
            item["code"] = item.get("cpt")
        if isinstance(item, dict) and "linked_icd10" not in item and item.get("linked_diagnosis_icd10"):
            item["linked_icd10"] = item.get("linked_diagnosis_icd10")

    service_items = _normalize_code_items(_get_key(parsed, "cpt_services", "services", "service_lines"))
    if service_items:
        parsed_cpt_items, parsed_em_items = _partition_service_items(service_items, index["enm"])
        if not cpt_items:
            cpt_items = parsed_cpt_items
        if not em_items:
            em_items = parsed_em_items

    icd10_codes = _normalize_icd10(
        _get_key(parsed, "ICD10_codes", "icd10_codes", "ICD10", "icd10", "icd10_diagnoses", "diagnoses")
    )
    modifiers_section = _normalize_modifiers(_get_key(parsed, "Modifiers", "modifiers"))
    reasoning = _get_key(parsed, "Reasoning", "reasoning")

    pre_gate_procedure_codes = [str(item.get("code") or "").strip() for item in cpt_items if str(item.get("code") or "").strip()]
    pre_gate_em_codes = [str(item.get("code") or "").strip() for item in em_items if str(item.get("code") or "").strip()]

    if procedure_candidate_codes:
        kept_items: List[Dict[str, Any]] = []
        for item in cpt_items:
            code = str(item.get("code") or "").strip()
            if code in procedure_candidate_codes:
                kept_items.append(item)
            elif code:
                dropped_procedure_codes.append(code)
        before = len(cpt_items)
        cpt_items = kept_items
        filtered = before - len(cpt_items)
        if filtered > 0:
            needs_review = True
            review_reasons.append(f"Filtered {filtered} procedure code(s) not present in procedure candidates.")

    if enm_candidate_codes:
        kept_items: List[Dict[str, Any]] = []
        for item in em_items:
            code = str(item.get("code") or "").strip()
            if code in enm_candidate_codes:
                kept_items.append(item)
            elif code:
                dropped_em_codes.append(code)
        before = len(em_items)
        em_items = kept_items
        filtered = before - len(em_items)
        if filtered > 0:
            needs_review = True
            review_reasons.append(f"Filtered {filtered} E/M code(s) not present in E/M candidates.")

    modifier_rules = list(index["modifiers"].values())
    state["modifier_rules"] = modifier_rules

    selected_cpts = []
    for item in cpt_items + em_items:
        code = item.get("code")
        if code:
            selected_cpts.append(str(code))
    state["selected_cpts"] = selected_cpts

    rows: List[Dict[str, Any]] = []
    modifier_decisions: List[Dict[str, Any]] = []
    em_decisions: List[Dict[str, Any]] = []
    modifier_map: Dict[str, List[str]] = {}
    global_modifiers: List[str] = []
    for mod in modifiers_section:
        modifier = mod.get("modifier")
        applies_to = mod.get("applies_to", [])
        if modifier:
            if modifier_candidate_codes and str(modifier).strip() not in modifier_candidate_codes:
                needs_review = True
                review_reasons.append(f"Dropped modifier {modifier} not present in modifier candidates.")
                dropped_modifiers.append(str(modifier).strip())
                continue
            normalized_targets = _normalize_list(applies_to)
            if not normalized_targets:
                global_modifiers.append(str(modifier))
                modifier_decisions.append(
                    {
                        "source": "llm_global",
                        "modifier": str(modifier),
                        "code": None,
                        "reason": "LLM returned modifier without CPT target; applied globally.",
                    }
                )
            for code in normalized_targets:
                modifier_map.setdefault(code, []).append(str(modifier))
                modifier_decisions.append(
                    {
                        "source": "llm_targeted",
                        "modifier": str(modifier),
                        "code": str(code),
                        "reason": "LLM explicitly targeted this CPT code.",
                    }
                )

    def build_row(item: Dict[str, Any]) -> None:
        code = str(item.get("code"))
        meta = index["procedures"].get(code) or index["enm"].get(code) or {}
        charge_per_unit_flag = _normalize_charge_per_unit(meta.get("ChargePerUnit"))
        charge_flag = "YES" if charge_per_unit_flag else "NO"

        qty_value = item.get("units", None)
        if qty_value is None:
            qty_value = item.get("qty", None)
        if qty_value is None:
            qty_value = item.get("quantity", None)
        try:
            qty = int(qty_value) if qty_value is not None else 1
        except (TypeError, ValueError):
            qty = 1

        # Modifiers should come from the LLM output (global + CPT-targeted),
        # not by blindly attaching every retrieved modifier reference.
        row_modifiers: List[str] = []
        row_modifiers.extend(global_modifiers)
        row_modifiers.extend(modifier_map.get(code, []))
        llm_item_modifiers = _normalize_list(item.get("modifiers"))
        accepted_llm_modifiers: List[str] = []
        for mod in llm_item_modifiers:
            if modifier_candidate_codes and str(mod).strip() not in modifier_candidate_codes:
                needs_review = True
                review_reasons.append(f"Dropped line-level modifier {mod} not present in modifier candidates.")
                dropped_modifiers.append(str(mod).strip())
                continue
            accepted_llm_modifiers.append(mod)
            modifier_decisions.append(
                {
                    "source": "llm_item",
                    "modifier": mod,
                    "code": code,
                    "reason": "Modifier present directly on LLM CPT/E&M item.",
                }
            )

        row_modifiers.extend(accepted_llm_modifiers)

        cleaned_modifiers: List[str] = []
        for m in row_modifiers:
            match = QTY_MOD_RE.match(str(m).strip())
            if match:
                n = int(match.group(1))
                qty = max(qty, n)
                continue
            cleaned_modifiers.append(m)

        rows.append(
            {
                "procedure": item.get("description") or meta.get("codeDesc"),
                "code": code,
                "modifiers": sorted({m for m in cleaned_modifiers if m}),
                "dx_codes": (
                    _normalize_list(item.get("linked_icd10"))
                    or _normalize_list(item.get("diagnosis_links"))
                    or _normalize_list(item.get("dx_codes"))
                    or icd10_codes
                ),
                "qty": qty,
                "charge_per_unit": charge_flag,
                "charge_unit": None,
                "charges": None,
            }
        )

    for item in cpt_items:
        build_row(item)
    for item in em_items:
        build_row(item)

    if em_items:
        for item in em_items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            em_decisions.append(
                {
                    "source": "llm_em",
                    "code": code,
                    "reason": "E/M code returned by LLM from note context.",
                }
            )
    else:
        em_like_codes = [
            code
            for code in selected_cpts
            if code in index["enm"] or str(code).startswith("99")
        ]
        if em_like_codes:
            for code in em_like_codes:
                em_decisions.append(
                    {
                        "source": "llm_em",
                        "code": code,
                        "reason": "E/M-like code detected in LLM output.",
                    }
                )
        else:
            llm_note = str(_get_key(parsed, "notes", "Notes") or "").strip()
            if llm_note:
                reason = llm_note
            elif cpt_items:
                reason = "No E/M code returned; encounter appears procedure-focused in this run."
            else:
                reason = "No E/M code returned by LLM."
            em_decisions.append(
                {
                    "source": "llm_no_em",
                    "code": None,
                    "reason": reason,
                }
            )

    if (cpt_items or em_items) and not rows:
        needs_review = True
        review_reasons.append("All code lines were removed during candidate gating.")

    if not rows:
        needs_review = True
        review_reasons.append("No billable rows produced; manual review required.")

    state["needs_review"] = needs_review
    state["review_reasons"] = review_reasons

    manual_review: Dict[str, Any] = {}
    if needs_review:
        manual_review = {
            "status": "needs_review",
            "reasons": review_reasons,
            "llm_requested_codes": {
                "procedure": sorted({code for code in pre_gate_procedure_codes if code}),
                "em": sorted({code for code in pre_gate_em_codes if code}),
            },
            "dropped": {
                "procedure": sorted({code for code in dropped_procedure_codes if code}),
                "em": sorted({code for code in dropped_em_codes if code}),
                "modifiers": sorted({code for code in dropped_modifiers if code}),
            },
            "candidate_alternatives": {
                "procedure": _top_candidate_summary(state.get("procedure_candidates"), 5),
                "em": _top_candidate_summary(state.get("enm_candidates"), 5),
                "modifier": _top_candidate_summary(state.get("modifier_candidates"), 8),
            },
        }
    state["manual_review"] = manual_review

    state["billing_result"] = {
        "rows": rows,
        "icd10_codes": icd10_codes,
        "modifier_decisions": modifier_decisions,
        "em_decisions": em_decisions,
        "reasoning": reasoning,
        "needs_review": needs_review,
        "review_reasons": review_reasons,
        "manual_review": manual_review,
        "raw_llm_output": llm_output,
    }

    return state

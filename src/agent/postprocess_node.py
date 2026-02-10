import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from src.agent.nodes import rule_applies


CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|```$", re.IGNORECASE)


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
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
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


async def postprocess_billing_node(state: BillingState) -> BillingState:
    billing_context = state.get("billing_context", {})
    llm_output = billing_context.get("llm_output", "")
    parsed = _parse_llm_json(llm_output)

    cpt_items = _normalize_code_items(_get_key(parsed, "CPT_codes", "cpt_codes", "CPT", "cpt"))
    em_items = _normalize_code_items(_get_key(parsed, "E_M_codes", "em_codes", "E/M", "em"))
    icd10_codes = _normalize_list(_get_key(parsed, "ICD10_codes", "icd10_codes", "ICD10", "icd10"))
    modifiers_section = _normalize_code_items(_get_key(parsed, "Modifiers", "modifiers"))
    reasoning = _get_key(parsed, "Reasoning", "reasoning")

    retrieval = state.get("retrieval", [])
    index = _index_retrieval(retrieval)

    modifier_rules = list(index["modifiers"].values())
    state["modifier_rules"] = modifier_rules

    selected_cpts = []
    for item in cpt_items + em_items:
        code = item.get("code")
        if code:
            selected_cpts.append(str(code))
    state["selected_cpts"] = selected_cpts

    rows: List[Dict[str, Any]] = []
    modifier_map: Dict[str, List[str]] = {}
    for mod in modifiers_section:
        modifier = mod.get("modifier")
        applies_to = mod.get("applies_to", [])
        if modifier:
            for code in _normalize_list(applies_to):
                modifier_map.setdefault(code, []).append(str(modifier))

    def build_row(item: Dict[str, Any]) -> None:
        code = str(item.get("code"))
        meta = index["procedures"].get(code) or index["enm"].get(code) or {}
        charge_per_unit = meta.get("ChargePerUnit")
        charge_flag = "Yes" if charge_per_unit else "No"

        row_modifiers: List[str] = []
        for rule in modifier_rules:
            if rule_applies(rule, state, code):
                modifier = rule.get("modifier")
                if modifier:
                    row_modifiers.append(str(modifier))
        row_modifiers.extend(modifier_map.get(code, []))
        row_modifiers.extend(_normalize_list(item.get("modifiers")))

        rows.append(
            {
                "procedure": item.get("description") or meta.get("codeDesc"),
                "code": code,
                "modifiers": sorted({m for m in row_modifiers if m}),
                "dx_codes": _normalize_list(item.get("linked_icd10")) or icd10_codes,
                "qty": item.get("units", 1),
                "charge_per_unit": charge_flag,
                "charge_unit": None,
                "charges": None,
            }
        )

    for item in cpt_items:
        build_row(item)
    for item in em_items:
        build_row(item)

    state["billing_result"] = {
        "rows": rows,
        "icd10_codes": icd10_codes,
        "reasoning": reasoning,
        "raw_llm_output": llm_output,
    }

    return state

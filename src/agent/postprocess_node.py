import json
import re
import sys
from html import escape
from pathlib import Path
from typing import Any, Dict, List

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from src.agent.state_helpers import _append_narrative


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
            code = (
                str(meta.get("modifier")) if meta.get("modifier") is not None else None
            )
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


def _resolve_charge_per_unit(meta: Dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    for key in ("ChargePerUnit", "chargePerUnit", "charge_per_unit"):
        if key in meta:
            return _normalize_charge_per_unit(meta.get(key))
    return False


def _resolve_qty(item: Dict[str, Any], meta: Dict[str, Any]) -> int:
    qty_value = item.get("units", None)
    if qty_value is None:
        qty_value = item.get("qty", None)
    if qty_value is None:
        qty_value = item.get("quantity", None)
    try:
        qty = int(qty_value) if qty_value is not None else 1
    except (TypeError, ValueError):
        qty = 1

    min_qty_raw = meta.get("minQty") if isinstance(meta, dict) else None
    max_qty_raw = meta.get("maxQty") if isinstance(meta, dict) else None

    try:
        min_qty = (
            int(min_qty_raw)
            if min_qty_raw is not None and str(min_qty_raw).strip() != ""
            else None
        )
    except (TypeError, ValueError):
        min_qty = None
    try:
        max_qty = (
            int(max_qty_raw)
            if max_qty_raw is not None and str(max_qty_raw).strip() != ""
            else None
        )
    except (TypeError, ValueError):
        max_qty = None

    if min_qty is not None:
        qty = max(qty, min_qty)
    if max_qty is not None and max_qty > 0:
        qty = min(qty, max_qty)
    return max(qty, 1)


def _dedupe_upper(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip().upper()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _line_dx_codes(item: Dict[str, Any], global_icd10: List[str]) -> List[str]:
    item_level = (
        _normalize_list(item.get("linked_icd10"))
        or _normalize_list(item.get("diagnosis_links"))
        or _normalize_list(item.get("dx_codes"))
    )
    if item_level:
        return _dedupe_upper(item_level)

    if len(global_icd10) == 1:
        return _dedupe_upper(global_icd10)

    return []


def _normalize_billing_party(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"ins", "insurance", "carrier", "payer"}:
        return "INS"
    if text in {"pat", "patient", "self", "self-pay", "self_pay"}:
        return "PAT"
    if text in {"nc", "non-covered", "noncovered", "no-charge", "no_charge"}:
        return "NC"
    return ""


def _extract_billing_party(item: Dict[str, Any]) -> str:
    for key in (
        "billing_party",
        "bill_to",
        "payer",
        "pay_type",
        "ins_pat_nc",
        "insurance_type",
    ):
        if key in item:
            party = _normalize_billing_party(item.get(key))
            if party:
                return party
    return ""


def _extract_money(item: Dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in item:
            continue
        raw = item.get(key)
        if raw is None:
            continue
        text = str(raw).strip().replace("$", "").replace(",", "")
        if not text:
            continue
        try:
            return float(text)
        except (TypeError, ValueError):
            continue
    return None


def _money_text(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:.2f}"


def _extract_item_modifiers(item: Dict[str, Any]) -> List[str]:
    return (
        _normalize_list(item.get("modifiers"))
        or _normalize_list(item.get("modifier"))
        or _normalize_list(item.get("modifierId"))
        or _normalize_list(item.get("modifier_id"))
    )


def _candidate_metadata_index(items: Any) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        metadata = item.get("metadata")
        if code and isinstance(metadata, dict):
            out[code] = metadata
    return out


# _append_narrative is imported from src.agent.state_helpers
def _normalize_date_of_service(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        return text.split("T", 1)[0]
    if " " in text:
        return text.split(" ", 1)[0]
    return text


def _build_billing_html_table(
    note_id: Any, date_of_service: Any, billing_result: Dict[str, Any]
) -> str:
    note_id_text = escape(str(note_id or ""))
    dos_text = escape(_normalize_date_of_service(date_of_service))
    rows = billing_result.get("rows", []) if isinstance(billing_result, dict) else []
    if not isinstance(rows, list):
        rows = []

    row_html: List[str] = []
    for row in rows:
        procedure = escape(str(row.get("procedure") or row.get("procedure_desc") or ""))
        code = escape(str(row.get("code") or ""))
        modifiers = row.get("modifiers")
        modifier_text = ""
        if isinstance(modifiers, list):
            modifier_text = ", ".join(
                str(mod).strip() for mod in modifiers if str(mod).strip()
            )
        else:
            modifier_text = str(modifiers or "").strip()

        qty = escape(str(row.get("qty") if row.get("qty") is not None else ""))
        charge_per_unit_raw = str(row.get("charge_per_unit") or "").strip().upper()
        charge_per_unit = "Yes" if charge_per_unit_raw == "YES" else "No"
        billing_party = str(row.get("billing_party") or "").upper()

        ins_checked = "◉" if billing_party == "INS" else "○"
        pat_checked = "◉" if billing_party == "PAT" else "○"
        nc_checked = "◉" if billing_party == "NC" else "○"

        dx_codes = row.get("dx_codes")
        if isinstance(dx_codes, list):
            dx_text = ", ".join(
                str(code).strip() for code in dx_codes if str(code).strip()
            )
        else:
            dx_text = str(dx_codes or "").strip()

        row_html.append(
            "    <tr>"
            f"<td>{procedure}</td>"
            f"<td>{code}</td>"
            f"<td>{escape(modifier_text)}</td>"
            f"<td>{escape(dx_text)}</td>"
            f"<td style='text-align:center'>{ins_checked}</td>"
            f"<td style='text-align:center'>{pat_checked}</td>"
            f"<td style='text-align:center'>{nc_checked}</td>"
            f"<td>{qty}</td>"
            f"<td>{charge_per_unit}</td>"
            "</tr>"
        )

    body = "\n".join(row_html)
    return (
        '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; width:100%;">\n'
        "  <thead>\n"
        "    <tr>\n"
        f'      <th colspan="9" style="text-align:left;">Note ID: {note_id_text} | DOS: {dos_text}</th>\n'
        "    </tr>\n"
        "    <tr>\n"
        "      <th>Procedures</th>\n"
        "      <th>Code</th>\n"
        "      <th>Modifier</th>\n"
        "      <th>Dx Code</th>\n"
        "      <th>Ins.</th>\n"
        "      <th>Pat.</th>\n"
        "      <th>NC</th>\n"
        "      <th>Qty.</th>\n"
        "      <th>Per Unit</th>\n"
        "    </tr>\n"
        "  </thead>\n"
        "  <tbody>\n"
        f"{body}\n"
        "  </tbody>\n"
        "</table>"
    )


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
    procedure_candidate_meta = _candidate_metadata_index(
        state.get("procedure_candidates")
    )
    enm_candidate_meta = _candidate_metadata_index(state.get("enm_candidates"))
    procedure_candidate_codes = _candidate_code_set(state.get("procedure_candidates"))
    enm_candidate_codes = _candidate_code_set(state.get("enm_candidates"))
    modifier_candidate_codes = _candidate_code_set(state.get("modifier_candidates"))
    needs_review = False
    review_reasons: List[str] = []
    dropped_procedure_codes: List[str] = []
    dropped_em_codes: List[str] = []
    dropped_modifiers: List[str] = []

    cpt_items = _normalize_code_items(
        _get_key(parsed, "CPT_codes", "cpt_codes", "CPT", "cpt", "procedures")
    )
    em_raw = _get_key(
        parsed, "E_M_codes", "em_codes", "E/M", "em", "evaluation_and_management"
    )
    em_items = _normalize_code_items(em_raw)
    if not em_items and isinstance(em_raw, dict):
        em_items = [em_raw]

    # Normalize alternate shape fields used by some model responses.
    for item in cpt_items:
        if isinstance(item, dict) and "code" not in item and item.get("cpt"):
            item["code"] = item.get("cpt")
        if (
            isinstance(item, dict)
            and "linked_icd10" not in item
            and item.get("linked_diagnosis_icd10")
        ):
            item["linked_icd10"] = item.get("linked_diagnosis_icd10")
    for item in em_items:
        if isinstance(item, dict) and "code" not in item and item.get("cpt"):
            item["code"] = item.get("cpt")
        if (
            isinstance(item, dict)
            and "linked_icd10" not in item
            and item.get("linked_diagnosis_icd10")
        ):
            item["linked_icd10"] = item.get("linked_diagnosis_icd10")

    service_items = _normalize_code_items(
        _get_key(parsed, "cpt_services", "services", "service_lines")
    )
    if service_items:
        parsed_cpt_items, parsed_em_items = _partition_service_items(
            service_items, index["enm"]
        )
        if not cpt_items:
            cpt_items = parsed_cpt_items
        if not em_items:
            em_items = parsed_em_items

    icd10_codes = _normalize_icd10(
        _get_key(
            parsed,
            "ICD10_codes",
            "icd10_codes",
            "ICD10",
            "icd10",
            "icd10_diagnoses",
            "diagnoses",
        )
    )
    modifiers_section = _normalize_modifiers(_get_key(parsed, "Modifiers", "modifiers"))
    reasoning = _get_key(parsed, "Reasoning", "reasoning")

    pre_gate_procedure_codes = [
        str(item.get("code") or "").strip()
        for item in cpt_items
        if str(item.get("code") or "").strip()
    ]
    pre_gate_em_codes = [
        str(item.get("code") or "").strip()
        for item in em_items
        if str(item.get("code") or "").strip()
    ]

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
            review_reasons.append(
                f"Filtered {filtered} procedure code(s) not present in procedure candidates."
            )

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
            review_reasons.append(
                f"Filtered {filtered} E/M code(s) not present in E/M candidates."
            )

    modifier_rules = list(index["modifiers"].values())
    retrieval_modifier_codes = {
        str(code).strip().upper()
        for code in index["modifiers"].keys()
        if str(code).strip()
    }
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
            normalized_modifier = str(modifier).strip().upper()
            if (
                modifier_candidate_codes
                and normalized_modifier not in {m.upper() for m in modifier_candidate_codes}
                and normalized_modifier not in retrieval_modifier_codes
            ):
                needs_review = True
                review_reasons.append(
                    f"Dropped modifier {normalized_modifier} not present in modifier candidates or retrieval references."
                )
                dropped_modifiers.append(normalized_modifier)
                continue
            normalized_targets = _normalize_list(applies_to)
            if not normalized_targets:
                global_modifiers.append(normalized_modifier)
                modifier_decisions.append(
                    {
                        "source": "llm_global",
                        "modifier": normalized_modifier,
                        "code": None,
                        "reason": "LLM returned modifier without CPT target; applied globally.",
                    }
                )
            for code in normalized_targets:
                modifier_map.setdefault(str(code).strip(), []).append(normalized_modifier)
                modifier_decisions.append(
                    {
                        "source": "llm_targeted",
                        "modifier": normalized_modifier,
                        "code": str(code),
                        "reason": "LLM explicitly targeted this CPT code.",
                    }
                )

    def build_row(item: Dict[str, Any]) -> None:
        nonlocal needs_review
        code = str(item.get("code"))
        meta = (
            index["procedures"].get(code)
            or index["enm"].get(code)
            or procedure_candidate_meta.get(code)
            or enm_candidate_meta.get(code)
            or {}
        )
        if not meta:
            needs_review = True
            review_reasons.append(
                f"Missing retrieval rule metadata for code {code}; charge per unit could not be sourced."
            )

        charge_per_unit_flag = _resolve_charge_per_unit(meta)
        charge_flag = "YES" if charge_per_unit_flag else "NO"

        qty = _resolve_qty(item, meta)
        billing_party = _extract_billing_party(item)
        charge_unit = _extract_money(
            item,
            "charge_unit",
            "charge_per_unit_amount",
            "unit_charge",
            "rate",
            "fee",
        )
        total_charges = _extract_money(
            item,
            "charges",
            "total_charge",
            "line_total",
        )
        if total_charges is None and charge_unit is not None:
            total_charges = charge_unit * qty

        # Modifiers should come from the LLM output (global + CPT-targeted),
        # not by blindly attaching every retrieved modifier reference.
        row_modifiers: List[str] = []
        row_modifiers.extend(global_modifiers)
        row_modifiers.extend(modifier_map.get(code, []))
        llm_item_modifiers = _extract_item_modifiers(item)
        accepted_llm_modifiers: List[str] = []
        for mod in llm_item_modifiers:
            normalized_mod = str(mod).strip().upper()
            if (
                modifier_candidate_codes
                and normalized_mod not in {m.upper() for m in modifier_candidate_codes}
                and normalized_mod not in retrieval_modifier_codes
            ):
                needs_review = True
                review_reasons.append(
                    f"Dropped line-level modifier {normalized_mod} not present in modifier candidates or retrieval references."
                )
                dropped_modifiers.append(normalized_mod)
                continue
            accepted_llm_modifiers.append(normalized_mod)
            modifier_decisions.append(
                {
                    "source": "llm_item",
                    "modifier": normalized_mod,
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

        linked_dx = _line_dx_codes(item, icd10_codes)
        if not linked_dx and len(icd10_codes) > 1:
            needs_review = True
            review_reasons.append(
                f"Code {code} has multiple encounter DX options but no explicit CPT↔DX linkage from model output."
            )

        rows.append(
            {
                "procedure": item.get("description") or meta.get("codeDesc"),
                "procedure_desc": item.get("description") or meta.get("codeDesc"),
                "code": code,
                "modifiers": sorted({str(m).strip().upper() for m in cleaned_modifiers if str(m).strip()}),
                "dx_codes": linked_dx,
                "dx_code": ", ".join(linked_dx),
                "billing_party": billing_party,
                "ins": billing_party == "INS",
                "pat": billing_party == "PAT",
                "nc": billing_party == "NC",
                "qty": qty,
                "charge_per_unit": charge_flag,
                "charge_unit": _money_text(charge_unit),
                "charges": _money_text(total_charges),
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
                "procedure": sorted(
                    {code for code in pre_gate_procedure_codes if code}
                ),
                "em": sorted({code for code in pre_gate_em_codes if code}),
            },
            "dropped": {
                "procedure": sorted({code for code in dropped_procedure_codes if code}),
                "em": sorted({code for code in dropped_em_codes if code}),
                "modifiers": sorted({code for code in dropped_modifiers if code}),
            },
            "candidate_alternatives": {
                "procedure": _top_candidate_summary(
                    state.get("procedure_candidates"), 5
                ),
                "em": _top_candidate_summary(state.get("enm_candidates"), 5),
                "modifier": _top_candidate_summary(state.get("modifier_candidates"), 8),
            },
        }
    state["manual_review"] = manual_review

    # Attach patient / visit / note identity so the API response is self-contained.
    notes_for_result = (
        state.get("notes", {}) if isinstance(state.get("notes"), dict) else {}
    )
    state["billing_result"] = {
        "note_id": state.get("note_id"),
        "patient": notes_for_result.get("patient"),
        "visit": notes_for_result.get("visit"),
        "rows": rows,
        "icd10_codes": icd10_codes,
        "modifier_decisions": modifier_decisions,
        "em_decisions": em_decisions,
        "reasoning": reasoning,
        "narrative_summary": state.get("narrative_summary", ""),
        "self_correction_notes": state.get("self_correction_notes", []),
        "needs_review": needs_review,
        "review_reasons": review_reasons,
        "manual_review": manual_review,
        "raw_llm_output": llm_output,
    }

    notes = state.get("notes", {}) if isinstance(state.get("notes"), dict) else {}
    visit = notes.get("visit", {}) if isinstance(notes.get("visit"), dict) else {}
    date_of_service = visit.get("date")
    billing_html_table = _build_billing_html_table(
        state.get("note_id"), date_of_service, state["billing_result"]
    )
    state["billing_result"]["html_table"] = billing_html_table
    state["html_table"] = billing_html_table

    return state

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from context.notes_context import notes_context
from context.biopsy_context import biopsy_context
from context.mohs_context import mohs_context
from context.prescriptions_context import prescriptions_context




async def notes_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["notes"] = {"error": "missing note_id"}
        return state
    state["notes"] = await notes_context(note_id)
    return state



async def biopsy_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["biopsy"] = {"error": "missing note_id"}
        return state
    state["biopsy"] = await biopsy_context(note_id)
    return state


async def mohs_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["mohs"] = {"error": "missing note_id"}
        return state
    state["mohs"] = await mohs_context(note_id)
    return state


async def prescriptions_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["prescriptions"] = {"error": "missing note_id"}
        return state
    state["prescriptions"] = await prescriptions_context(
        state=state,  # type: ignore
        note_id=note_id,
    )
    return state



async def billing_reasoning_node(state: BillingState) -> BillingState:
    notes = state.get("notes", {})
    state["billing_context"] = {
        "patient": notes.get("patient"),
        "diagnoses": notes.get("diagnoses"),
        "procedures": notes.get("procedures_documented"),
        "biopsy": state.get("biopsy", {}),
        "mohs": state.get("mohs", {}),
        "medications": state.get("prescriptions", {}),
    }
    return state




def charge_per_unit_node(state: BillingState) -> BillingState:
    billed_items = []
    billing_result = state.get("billing_result", {})
    procedures = billing_result.get("procedures", [])

    def to_int(val: object) -> int | None:
        try:
            return int(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    for item in procedures:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule", {})
        actual_qty = item.get("quantity", 1)

        if rule.get("ChargePerUnit"):
            qty = actual_qty
            min_qty = to_int(rule.get("minQty"))
            max_qty = to_int(rule.get("maxQty"))
            if min_qty is not None:
                qty = max(qty, min_qty)
            if max_qty is not None:
                qty = min(qty, max_qty)
        else:
            qty = 1

        billed_items.append({
            "cpt": item.get("cpt"),
            "units": qty,
            "charge_per_unit": rule.get("ChargePerUnit"),
            "reason": "Charge per unit applied" if rule.get("ChargePerUnit") else "Single charge rule",
        })

    billing_result["final_charges"] = billed_items
    state["billing_result"] = billing_result
    return state


def size_filter_node(state: BillingState) -> BillingState:
    parsed = state.get("parsed_procedure", {})
    procedure_size = parsed.get("size_cm") if isinstance(parsed, dict) else None

    def to_float(val: object) -> float | None:
        try:
            return float(val)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    size_value = to_float(procedure_size)
    if size_value is None:
        state["eligible_procedure_codes"] = []
        return state

    valid_codes = []
    for rule in state.get("retrieval", []):
        if not isinstance(rule, dict):
            continue
        meta = rule.get("metadata", {})
        min_size = to_float(meta.get("minSize"))
        max_size = to_float(meta.get("maxSize"))

        min_size = 0.0 if min_size is None else min_size
        max_size = 999.0 if max_size is None else max_size

        if min_size <= size_value <= max_size:
            valid_codes.append(rule)

    state["eligible_procedure_codes"] = valid_codes
    return state




def rule_applies(rule: dict, state: BillingState, cpt: str) -> bool:
    if not isinstance(rule, dict):
        return False
    if not rule.get("active", True):
        return False
    if rule.get("enmModifier"):
        notes = state.get("notes", {})
        visit = notes.get("visit", {})
        return bool(visit)
    return True


def modifier_node(state: BillingState) -> BillingState:
    applied = []
    selected_cpts = state.get("selected_cpts", [])
    modifier_rules = state.get("modifier_rules", [])

    for cpt in selected_cpts:
        modifiers = []

        for rule in modifier_rules:
            if rule_applies(rule, state, cpt):
                modifiers.append(rule.get("modifier"))

        applied.append({
            "cpt": cpt,
            "modifiers": [m for m in modifiers if m],
        })

    state["final_cpts"] = applied
    return state

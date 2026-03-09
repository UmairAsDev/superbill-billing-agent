import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from context.notes_context import notes_context
from context.biopsy_context import biopsy_context
from context.mohs_context import mohs_context
from context.prescriptions_context import prescriptions_context
from context.general_context import general_context
from src.agent.state_helpers import _append_narrative


def _compact_text(value: object, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _notes_narrative(notes: dict) -> str:
    patient = notes.get("patient", {}) if isinstance(notes.get("patient"), dict) else {}
    visit = notes.get("visit", {}) if isinstance(notes.get("visit"), dict) else {}
    chief = _compact_text(notes.get("chief_complaint"), 160)
    procedures = _compact_text(notes.get("procedures_documented"), 180)
    diagnoses = _compact_text(notes.get("diagnoses"), 180)
    return (
        f"Encounter: age={patient.get('age')} gender={patient.get('gender')} "
        f"date={visit.get('date')} POS={visit.get('place_of_service')} | "
        f"chief_complaint={chief} | procedures={procedures} | diagnoses={diagnoses}"
    )


async def notes_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["notes"] = {"error": "missing note_id"}
        _append_narrative(state, "notes_node: missing note_id")
        return state
    state["notes"] = await notes_context(note_id)
    notes = state.get("notes", {}) if isinstance(state.get("notes"), dict) else {}
    _append_narrative(state, f"notes_node: {_notes_narrative(notes)}")
    return state


async def biopsy_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["biopsy"] = {"error": "missing note_id"}
        _append_narrative(state, "biopsy_node: missing note_id")
        return state
    state["biopsy"] = await biopsy_context(note_id)
    biopsy = state.get("biopsy", {}) if isinstance(state.get("biopsy"), dict) else {}
    biopsy_info = (
        biopsy.get("biopsy", {}) if isinstance(biopsy.get("biopsy"), dict) else {}
    )
    _append_narrative(
        state,
        f"biopsy_node: performed={biopsy_info.get('performed')} count={biopsy_info.get('count', 0)}",
    )
    return state


async def mohs_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["mohs"] = {"error": "missing note_id"}
        _append_narrative(state, "mohs_node: missing note_id")
        return state
    state["mohs"] = await mohs_context(note_id)
    mohs = state.get("mohs", {}) if isinstance(state.get("mohs"), dict) else {}
    mohs_info = mohs.get("mohs", {}) if isinstance(mohs.get("mohs"), dict) else {}
    _append_narrative(
        state,
        f"mohs_node: performed={mohs_info.get('performed')} count={mohs_info.get('count', 0)}",
    )
    return state


async def prescriptions_node(state: BillingState) -> BillingState:
    note_id = state.get("note_id")
    if note_id is None:
        state["prescriptions"] = {"error": "missing note_id"}
        _append_narrative(state, "prescriptions_node: missing note_id")
        return state
    state["prescriptions"] = await prescriptions_context(
        state=state,  # type: ignore
        note_id=note_id,
    )
    prescriptions = (
        state.get("prescriptions", {})
        if isinstance(state.get("prescriptions"), dict)
        else {}
    )
    meds = (
        prescriptions.get("prescription", [])
        if isinstance(prescriptions.get("prescription"), list)
        else []
    )
    _append_narrative(state, f"prescriptions_node: active_rx_count={len(meds)}")
    return state


async def general_node(state: BillingState) -> BillingState:
    """Fetch general procedure details (pnAssessmentProDet) and add to state."""
    note_id = state.get("note_id")
    if note_id is None:
        state["general"] = {"error": "missing note_id"}
        _append_narrative(state, "general_node: missing note_id")
        return state
    state["general"] = await general_context(note_id)
    general = state.get("general", {}) if isinstance(state.get("general"), dict) else {}
    count = general.get("count", 0) if isinstance(general, dict) else 0
    _append_narrative(state, f"general_node: general_procedure_count={count}")
    return state


async def billing_reasoning_node(state: BillingState) -> BillingState:
    notes = state.get("notes", {})
    state["billing_context"] = {
        "patient": notes.get("patient"),
        "diagnoses": notes.get("diagnoses"),
        "procedures": notes.get("procedures_documented"),
        "biopsy": state.get("biopsy", {}),
        "mohs": state.get("mohs", {}),
        "general": state.get("general", {}),
        "medications": state.get("prescriptions", {}),
        "narrative_summary": state.get("narrative_summary", ""),
    }
    _append_narrative(
        state, "billing_reasoning_node: consolidated context for retrieval and coding"
    )
    return state

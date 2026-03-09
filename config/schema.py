from typing import TypedDict, List, Dict, Any


class BillingState(TypedDict, total=False):
    note_id: int
    narrative_summary: str
    notes: Dict[str, Any]
    biopsy: Dict[str, Any]
    mohs: Dict[str, Any]
    general: Dict[str, Any]
    prescriptions: Dict[str, Any]
    billing_context: Dict[str, Any]
    retrieval: List[Dict[str, Any]]
    encounter_facts: Dict[str, Any]
    procedure_candidates: List[Dict[str, Any]]
    enm_candidates: List[Dict[str, Any]]
    modifier_candidates: List[Dict[str, Any]]
    candidate_reasoning: List[Dict[str, Any]]
    needs_review: bool
    review_reasons: List[str]
    manual_review: Dict[str, Any]
    html_table: str
    self_correction_notes: List[str]
    billing_result: Dict[str, Any]
    selected_cpts: List[str]
    modifier_rules: List[Dict[str, Any]]

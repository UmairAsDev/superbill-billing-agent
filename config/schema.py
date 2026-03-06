from typing import TypedDict, List, Dict, Any

class BillingState(TypedDict, total=False):
    note_id: int
    notes: Dict[str, Any]
    biopsy: Dict[str, Any]
    mohs: Dict[str, Any]
    prescriptions: Dict[str, Any]
    billing_context: Dict[str, Any]
    retrieved_data: Dict[str, Any]
    retrieval: List[Dict[str, Any]]
    encounter_facts: Dict[str, Any]
    procedure_candidates: List[Dict[str, Any]]
    enm_candidates: List[Dict[str, Any]]
    modifier_candidates: List[Dict[str, Any]]
    candidate_reasoning: List[Dict[str, Any]]
    needs_review: bool
    review_reasons: List[str]
    manual_review: Dict[str, Any]

    billing_result: Dict[str, Any]
    parsed_procedure: Dict[str, Any]
    selected_cpts: List[str]
    modifier_rules: List[Dict[str, Any]]
    final_cpts: List[Dict[str, Any]]
    eligible_procedure_codes: List[Dict[str, Any]]
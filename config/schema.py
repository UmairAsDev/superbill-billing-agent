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

    billing_result: Dict[str, Any]
    parsed_procedure: Dict[str, Any]
    selected_cpts: List[str]
    modifier_rules: List[Dict[str, Any]]
    final_cpts: List[Dict[str, Any]]
    eligible_procedure_codes: List[Dict[str, Any]]
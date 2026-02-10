
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from services.llm_factory import get_openai_llm
from config.schema import BillingState
from src.services.prompts import billing_prompt


async def billing_llm_node(state: BillingState) -> BillingState:
    llm = get_openai_llm()

    chain = billing_prompt | llm

    notes = state.get("notes", {})

    response = await chain.ainvoke(
        {
            "patient": notes.get("patient"),
            "visit": notes.get("visit"),
            "diagnoses": notes.get("diagnoses"),
            "procedures": notes.get("procedures_documented"),
            "biopsy": state.get("biopsy", {}),
            "mohs": state.get("mohs", {}),
            "medications": state.get("prescriptions", {}),
        }
    )

    state["billing_context"] = {
        "llm_output": response.content,
    }
    return state







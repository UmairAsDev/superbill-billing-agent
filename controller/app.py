from fastapi import APIRouter
from config.schema import BillingState
from src.agent.graph import build_billing_graph

router = APIRouter()




@router.post("/process_note/{note_id}")
async def process_note(note_id: int):
    graph = build_billing_graph()
    initial_state: BillingState = {"note_id": note_id}
    final_state = await graph.ainvoke(initial_state)
    return final_state
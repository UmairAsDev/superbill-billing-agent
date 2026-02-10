import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from langgraph.graph import StateGraph, END
from config.schema import BillingState
from src.agent.nodes import (
	notes_node,
	biopsy_node,
	mohs_node,
	prescriptions_node,
	billing_reasoning_node,
)
from src.agent.retrieval_node import retrieval_node
from src.agent.llm_node import billing_llm_node
from src.agent.postprocess_node import postprocess_billing_node


def build_billing_graph():
	graph = StateGraph(BillingState)

	graph.add_node("notes", notes_node)
	graph.add_node("biopsy", biopsy_node)
	graph.add_node("mohs", mohs_node)
	graph.add_node("prescriptions", prescriptions_node)
	graph.add_node("retrieval", retrieval_node)
	graph.add_node("billing_reasoning", billing_reasoning_node)
	graph.add_node("billing_llm", billing_llm_node)
	graph.add_node("postprocess", postprocess_billing_node)

	graph.set_entry_point("notes")
	graph.add_edge("notes", "biopsy")
	graph.add_edge("biopsy", "mohs")
	graph.add_edge("mohs", "prescriptions")
	graph.add_edge("prescriptions", "retrieval")
	graph.add_edge("retrieval", "billing_reasoning")
	graph.add_edge("billing_reasoning", "billing_llm")
	graph.add_edge("billing_llm", "postprocess")
	graph.add_edge("postprocess", END)

	return graph.compile()


__all__ = ["build_billing_graph"]

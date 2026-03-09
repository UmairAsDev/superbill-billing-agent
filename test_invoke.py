import asyncio
from src.agent.graph import build_billing_graph
from config.schema import BillingState

async def main():
    graph = build_billing_graph()
    state = BillingState(note_id=703566)
    print("Starting graph...")
    result = await graph.ainvoke(state)
    print("Done!")
    from pprint import pprint
    pprint(result.get('billing_result'))

if __name__ == "__main__":
    asyncio.run(main())

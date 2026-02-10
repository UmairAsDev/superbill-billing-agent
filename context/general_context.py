import sys
import asyncio
from pathlib import Path
from typing import Sequence, Any
from sqlalchemy.engine import RowMapping
sys.path.append(str(Path(__file__).parent.parent))
from src.services.general import general_notes, prescription_notes, previous_superbill, previous_medications
from database.conn import async_engine
from loguru import logger
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

logger.add("logs/general_context.log", rotation="10 MB")

async def general_context(note_id: int) -> dict[str, Any]:

    try:
        general_data = await general_notes(note_id) or []
        if not general_data:
            return {"general": {"performed": False, "count": 0, "details": []}}

        general_details = []
        for item in general_data:
            if not isinstance(item, dict):
                continue  
            general_details.append({
                "procedure_name": item.get("proName"),
                "technique": item.get("method"),
                "site": item.get("site"),
                "location": item.get("location"),
                "choice": item.get("choice"),
                "quality": item.get("qty"),
                "billingSize": item.get("billingSize"),
            })
        return {
            "general": general_details,
            "count": len(general_details),
            "performed": True
        }
    except Exception as e:
        logger.error(f"Error in general_context: {e}")
        return {"error": str(e)}
        

        
if __name__ == "__main__":
    test_note_id = 671744
    result = asyncio.run(general_context(test_note_id))
    print(result)
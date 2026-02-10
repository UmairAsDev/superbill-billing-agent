import sys
import asyncio
from pathlib import Path
from typing import Sequence, Any
from sqlalchemy.engine import RowMapping
sys.path.append(str(Path(__file__).parent.parent))
from src.services.mohs import mohs_notes
from database.conn import async_engine
from loguru import logger
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

logger.add("logs/mohs_context.log", rotation="10 MB")



async def mohs_context(note_id: int) -> dict[str, Any]:
    try:
        mohs_data = await mohs_notes(note_id) or []
        if not mohs_data:
            return {"mohs": {"performed": False, "count": 0, "details": []}}

        details = []
        for item in mohs_data:
            if not isinstance(item, dict):
                continue 
            details.append({
                "procedure_name": item.get("proName"),
                "site": item.get("site"),
                "location": item.get("location"),
                "pre_op_size": item.get("preOpSize"),
                "cleansing": item.get("cleansing"),
                "anesthesia": item.get("anesthesia"),
                "pre_mohs_note": item.get("preMohsNote"),
                "post_mohs_size_linear": item.get("postMohsSizeLinear"),
                "mohs_note": item.get("mohsNote"),
                "post_mohs_size": item.get("postMohsSize"),
                "undermining_size": item.get("underminingSize"),
                "int_suture": item.get("intSuture"),
                "int_suture_size": item.get("intSutureSize"),
                "ext_suture": item.get("extSuture"),
                "ext_suture_size": item.get("extSutureSize"),
            })

        return {
            "mohs": {
                "performed": True,
                "count": len(details),
                "details": details
            }
        }

    except Exception as e:
        logger.error(f"Error in mohs_context: {e}")
        return {"error": str(e)}
    finally:
        await async_engine.dispose()



if __name__ == "__main__":
    test_note_id = 703199
    result = asyncio.run(mohs_context(test_note_id))
    print(result)
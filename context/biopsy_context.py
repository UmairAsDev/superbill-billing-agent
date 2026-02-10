import sys
import asyncio
from pathlib import Path
from typing import Sequence
from sqlalchemy.engine import RowMapping
sys.path.append(str(Path(__file__).parent.parent))
from src.services.biopsy import biopsy_notes
from utils.helper import parse_size
from database.conn import async_engine
from loguru import logger
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

logger.add("logs/mohs_context.log", rotation="10 MB")





async def biopsy_context(note_id: int) -> dict:
    try:
        biopsy_data = await biopsy_notes(note_id) or []

        details = []
        for item in biopsy_data:
            if not isinstance(item, dict):
                continue

            details.append({
                "technique": item.get("method"),
                "site": item.get("site"),
                "laterality": item.get("location"),
                "rule_out_diagnosis": item.get("ruleOutDx"),
                "pathology_submitted": bool(item.get("pathology")),
                "frozen_section": bool(item.get("frozenSection")),
                "anesthesia": item.get("anesthesia"),
                "dressing": item.get("dressing"),
                "wound_size": parse_size(item.get("woundSize")), #type: ignore
                "closure_size": parse_size(item.get("closureSize")), #type: ignore
                "int_suture_size": item.get("intSutureSize"),
            })

        return {
            "biopsy": {
                "performed": bool(details),
                "count": len(details),
                "details": details,
            }
        }

    except Exception as e:
        logger.error(f"Error in biopsy_context: {e}")
        return {"error": str(e)}




if __name__ == "__main__":
    test_note_id = 711231
    result = asyncio.run(biopsy_context(test_note_id))
    print(result)
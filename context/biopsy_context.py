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

        def to_float(val: object) -> float | None:
            try:
                return float(val)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        def parse_cm_area(value: object) -> dict:
            """Parse stored strings like 'cm,Area,1.2-1' into friendly numbers."""
            if not isinstance(value, str) or not value:
                return {"raw": value, "unit": None, "length_cm": None, "width_cm": None, "max_dimension_cm": None}
            raw = value
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            unit = parts[0] if parts else None
            dims = parts[-1] if parts else ""

            length = width = None
            if "-" in dims:
                a, b = dims.split("-", 1)
                length = to_float(a)
                width = to_float(b)
            elif "x" in dims.lower():
                size = parse_size(dims)
                length = to_float(size.get("length"))
                width = to_float(size.get("width"))

            max_dim = None
            if length is not None and width is not None:
                max_dim = max(length, width)
            elif length is not None:
                max_dim = length
            elif width is not None:
                max_dim = width

            return {
                "raw": raw,
                "unit": unit,
                "length_cm": length,
                "width_cm": width,
                "max_dimension_cm": max_dim,
            }

        details = []
        for item in biopsy_data:
            if not isinstance(item, dict):
                continue

            procedure_name = item.get("proName")
            lesion_size = parse_cm_area(item.get("lesionSize"))
            wound_size = parse_cm_area(item.get("woundSize"))
            closure_size = parse_cm_area(item.get("closureSize"))
            undermining_size = parse_cm_area(item.get("underminingSize"))

            has_deep_sutures = bool(item.get("intSuture"))
            has_superficial_sutures = bool(item.get("extSuture"))

            undermining = bool(item.get("undermining"))
            dog_ear = bool(item.get("dogEar"))
            flap_closure = item.get("flapClosure")
            has_flap_closure = bool(flap_closure) and str(flap_closure).strip().lower() not in {"null", "none", "0"}

            if undermining or dog_ear or has_flap_closure:
                closure_hint = "complex"
            elif has_deep_sutures and has_superficial_sutures:
                closure_hint = "layered"
            else:
                closure_hint = None
            procedure_category = None
            if isinstance(procedure_name, str):
                low = procedure_name.lower()
                if "excision" in low:
                    procedure_category = "excision"
                elif "biopsy" in low:
                    procedure_category = "biopsy"

            details.append({
                "procedure_name": procedure_name,
                "procedure_category": procedure_category,
                "technique": item.get("method"),
                "site": item.get("site"),
                "laterality": item.get("location"),
                "rule_out_diagnosis": item.get("ruleOutDx"),
                "lesion_size": lesion_size,
                "margins_checked": item.get("checkMargin"),
                "margin_options": item.get("marginOptions"),
                "undermining": undermining,
                "undermining_size": undermining_size,
                "dog_ear": dog_ear,
                "dog_ear_count": item.get("dogEarCount"),
                "flap_closure": flap_closure,
                "pathology_submitted": bool(item.get("pathology")),
                "frozen_section": bool(item.get("frozenSection")),
                "anesthesia": item.get("anesthesia"),
                "dressing": item.get("dressing"),
                "wound_size": wound_size,
                "closure_size": closure_size,
                "closure_hint": closure_hint,
                "int_suture_size": item.get("intSutureSize"),
                "ext_suture_size": item.get("extSutureSize"),
                "repair_date": item.get("repairDate"),
                "notes": item.get("notes"),
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

    finally:
        await async_engine.dispose()




if __name__ == "__main__":
    test_note_id = 711231
    result = asyncio.run(biopsy_context(test_note_id))
    print(result)
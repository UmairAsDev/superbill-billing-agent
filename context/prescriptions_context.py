import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.services.general import prescription_notes, previous_medications, previous_superbill
from database.conn import async_engine
from loguru import logger
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

logger.add("logs/prescriptions_context.log", rotation="10 MB")


async def prescriptions_context(state: dict, note_id: int) -> dict:
    try:
        patient_id = state.get("notes", {}).get("patient", {}).get("patient_id")

        prescription_data = await prescription_notes(note_id)
        superbill_data = await previous_superbill(note_id)

        previous_medication = (
            await previous_medications(note_id, patient_id)
            if patient_id
            else []
        )

        return {
            "prescription": prescription_data,
            "previous_superbill": superbill_data,
            "previous_medications": previous_medication,
        }

    except Exception as e:
        logger.error(f"Error in prescriptions_context: {e}")
        return {"error": str(e)}
        
        
if __name__ == "__main__":
    test_note_id = 700436
    test_state = {"notes": {"patient": {"patient_id": 12345}}}
    result = asyncio.run(prescriptions_context(test_state, test_note_id))
    print(result)
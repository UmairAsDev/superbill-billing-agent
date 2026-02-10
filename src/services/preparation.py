import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.services.notes import notes
from src.services.general import general_notes, prescription_notes, previous_superbill, previous_medications
from loguru import logger
from database.conn import async_engine
from utils.helper import clean_html


logger.add("logs/preparation.log", rotation="10 MB")



async def prepare_data(note_id: int):
    try:
        note_data = await notes(note_id)
        patientId = None
        cleaned_data = clean_html(note_data) if note_data else None  # type: ignore
        if cleaned_data and isinstance(cleaned_data, list) and isinstance(cleaned_data[0], dict):
            patientId = cleaned_data[0].get("patientId")
        general_data = await general_notes(note_id)
        prescription_data = await prescription_notes(note_id)
        superbill_data = await previous_superbill(note_id)
        previous_medication = await previous_medications(note_id, patientId) if patientId else {}

        aggregated_data = {
            "note": cleaned_data,
            "general": general_data,
            "prescription": prescription_data,
            "previous_superbill": superbill_data,
            "previous_medications": previous_medication
        }
        return aggregated_data
    finally:
        await async_engine.dispose()






if __name__ == "__main__":
    test_note_id = 700436
    result = asyncio.run(prepare_data(test_note_id))
    print(result)
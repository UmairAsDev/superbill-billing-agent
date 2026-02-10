import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.services.notes import notes
from utils.helper import clean_html, extract_age, extract_gender
from database.conn import async_engine
from loguru import logger
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

logger.add("logs/notes_context.log", rotation="10 MB")




async def notes_context(note_id: int) -> dict:
    try:
        raw = await notes(note_id)
        cleaned = clean_html(raw)

        note = cleaned[0] if isinstance(cleaned, list) and cleaned else {}
        patient_summary = note.get("patientSummary", "")

        return {
            "patient": {
                "patient_id": note.get("patientId"),
                "age": extract_age(patient_summary),
                "gender": extract_gender(patient_summary),
            },
            "visit": {
                "date": note.get("noteDate"),
                "place_of_service": note.get("PlaceOfService"),
            },
            "chief_complaint": note.get("complaints"),
            "history": {
                "past_medical": note.get("pastHistory"),
                "review_of_systems": note.get("reviewofsystem"),
                "allergies": note.get("allergy"),
            },
            "assessment": note.get("assesment"),
            "diagnoses": note.get("diagnoses"),
            "exam": note.get("examination"),
            "procedures_documented": note.get("procedure"),

            "procedure_flags": {
                "biopsy_performed": bool(note.get("biopsyNotes")),
                "mohs_performed": bool(note.get("mohsNotes")),
            },

            "medications": {
                "current": note.get("currentmedication"),
            },

            "raw_patient_summary": patient_summary,
        }

    except Exception as e:
        logger.error(f"Error in notes_context: {e}")
        return {"error": str(e)}

    finally:
        await async_engine.dispose()
        







if __name__ == "__main__":
    test_note_id = 700436
    result = asyncio.run(notes_context(test_note_id))
    print(result)
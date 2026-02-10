import re
from bs4 import BeautifulSoup
from loguru import logger
import copy


def html_parser(html_content: str) -> str:
    if not isinstance(html_content, str):
        return ""
    text = BeautifulSoup(html_content, "html.parser").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()




def clean_html(notes_data:list[dict]) -> list[dict]:
    """Clean the notes data by removing HTML tags."""
    
    try:
        if not notes_data or not isinstance(notes_data, list):
            raise ValueError("Invalid data passed to clean_html_tags_safe")


        cleaned = [dict(note) for note in notes_data]

        fields_to_clean = [
            "biopsyNotes",
            "examination",
            "patientSummary",
            "complaints",
            "currentmedication",
            "pastHistory",
            "reviewofsystem",
            "assesment",
            "procedure",
            "mohsNotes",
            "allergy",
        ]

        for note in cleaned:
            logger.info(f"Cleaning HTML tags for note ID: {note.get('noteId', 'Unknown')}")
            
            for field in fields_to_clean:
                if field in note and note[field]:
                    note[field] = html_parser(note[field])

        return cleaned

    except Exception as e:
        logger.error(f"Error in clean_html_tags: {e}")
        return []




def extract_age(patient_summary: str) -> str:
    """Extract age from the patient summary."""
    if not patient_summary or not isinstance(patient_summary, str):
        return "Unknown"
    
    age_match = re.search(r'(\d{1,3})\s*years?', patient_summary, re.IGNORECASE)
    if age_match:
        return age_match.group(1)
    
    return "Unknown"


def extract_gender(patient_summary: str) -> str:
    """Extract gender from the patient summary."""
    if not patient_summary or not isinstance(patient_summary, str):
        return "Unknown"
    gender_match = re.search(r'([Mm]ale|[Ff]emale|[Oo]ther)', patient_summary)
    if gender_match:
        return gender_match.group(1).capitalize()
    return "Unknown"




def parse_size(size_str: str) -> dict[str, str]:
    """Parse size information from a string."""
    if not size_str or not isinstance(size_str, str):
        return {"length": "Unknown", "width": "Unknown"}
    
    size_match = re.search(r'(\d{1,2}\.?\d*)\s*x\s*(\d{1,2}\.?\d*)', size_str)
    if size_match:
        return {"length": size_match.group(1), "width": size_match.group(2)}
    
    return {"length": "Unknown", "width": "Unknown"}
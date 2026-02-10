from langchain_core.prompts import ChatPromptTemplate



billing_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a medical billing expert.
Generate CPT and ICD-10 codes based strictly on the provided context.
Follow US dermatology billing rules.
Explain reasoning briefly."""
    ),
    (
        "human",
        """
Patient Info:
{patient}

Visit Info:
{visit}

Diagnoses:
{diagnoses}

Procedures:
{procedures}

Biopsy:
{biopsy}

Mohs:
{mohs}

Medications & History:
{medications}

Instructions:
if modifiers are needed, include them in the output.

Return JSON with:
- CPT codes
- E/M codes (if applicable)
- ICD-10 codes
- Modifiers
- Reasoning
"""
    )
])



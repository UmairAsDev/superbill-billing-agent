"""
Shared helpers for all agent nodes.

Centralises the _append_narrative utility and the ICD-10 regex so they are
not copy-pasted across every node file.
"""

import re
from config.schema import BillingState

# ---------------------------------------------------------------------------
# ICD-10 regex (shared between fact_extractor_node and candidate_selection_node)
# ---------------------------------------------------------------------------
ICD_RE = re.compile(r"\b[A-TV-Z][0-9][0-9AB](?:\.[0-9A-TV-Z]{1,4})?\b")


# ---------------------------------------------------------------------------
# Narrative helper
# ---------------------------------------------------------------------------
def _append_narrative(state: BillingState, line: str, max_len: int = 320) -> None:
    """Append a concise line to the running narrative summary in *state*."""
    text = " ".join(str(line or "").split())
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    current = str(state.get("narrative_summary") or "").strip()
    state["narrative_summary"] = f"{current}\n{text}".strip() if current else text


__all__ = ["ICD_RE", "_append_narrative"]

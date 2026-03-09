import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))
from sqlalchemy import text
from database.deps import async_db_session
from loguru import logger

logger.add("logs/general.log", rotation="10 MB")


async def general_notes(note_id: int):
    """Fetch general procedure notes for a given note ID."""
    async with async_db_session() as db:
        general_query = text(
            """
        SELECT
        papd.noteId, pl.proName, papd.proSeqNo, pml.`method`, pcl.choice, sl.site, sll.location,
        papd.qty, papd.billingSize, papd.drugId, pl.drugName, papd.drugUnit, papd.proSiteLocation
        FROM pnAssessmentProDet papd
        LEFT JOIN proList pl ON pl.proId = papd.proId
        LEFT JOIN pathMethodList pml ON pml.methodId = papd.methodId
        LEFT JOIN proChoiceList pcl ON pcl.choiceId = papd.choiceId
        LEFT JOIN siteList sl ON sl.siteId = papd.siteId
        LEFT JOIN siteLocationList sll ON sll.locationId = papd.locationId
        WHERE papd.noteId = :note_id
        """
        )
        result = await db.execute(general_query, {"note_id": note_id})
        rows = result.mappings().all()
        if not rows:
            return []
        return [dict(row) for row in rows]


async def prescription_notes(note_id: int):
    """Fetch prescription notes for a given note ID."""
    async with async_db_session() as db:
        prescription_query = text(
            """
        SELECT * FROM erxPrescriptions WHERE progressnoteId = :note_id
        """
        )
        result = await db.execute(prescription_query, {"note_id": note_id})
        rows = result.mappings().all()
        if not rows:
            return []
        return [dict(row) for row in rows]


async def previous_superbill(note_id: int):
    """Fetch previous superbill data for the note immediately preceding note_id."""
    async with async_db_session() as db:
        superbill_query = text(
            """
        SELECT CASE WHEN p.enmCodeId > 0 THEN ecl.enmCodeDesc ELSE pl.proName END as `Procedure`,
        CASE WHEN p.enmCodeId > 0 THEN ecl.enmCode ELSE pcl.proCode END as `CPT`,
        p.modifierId,
        CASE WHEN p.chargePerUnit = 1 THEN 'YES' ELSE 'NO' END as `Charge Per Unit`,
        p.qty AS Quantity,
        GROUP_CONCAT(dc.icd10Code SEPARATOR ', ')
        FROM pnSB p
        LEFT JOIN pnSBAssessment ps ON ps.sBId = p.sBId
        LEFT JOIN diagnosisCodes dc ON dc.dxId = ps.dxId AND dc.dxCodeId = ps.dxCodeId
        LEFT JOIN proCodeList pcl ON pcl.proCodeId = p.proCodeId
        LEFT JOIN proList pl ON pl.proId = p.proId
        LEFT JOIN enmCodeList ecl ON ecl.enmCodeId = p.enmCodeId
        WHERE noteId = :note_id
        GROUP BY ps.sBId
        """
        )
        result = await db.execute(superbill_query, {"note_id": note_id})
        rows = result.mappings().all()
        if not rows:
            return []
        return [dict(row) for row in rows]


async def previous_medications(note_id: int, patient_id: int):
    """Fetch the most recent prior note's medication data for the patient."""
    async with async_db_session() as db:
        medication_query = text(
            """
        SELECT * FROM progressNotes WHERE noteId < :note_id AND patientId = :patient_id and pathNote = 0 ORDER BY noteId DESC LIMIT 1
        """
        )
        result = await db.execute(
            medication_query, {"note_id": note_id, "patient_id": patient_id}
        )
        rows = result.mappings().all()
        if not rows:
            return []
        return [dict(row) for row in rows]


async def main():
    from database.conn import async_engine

    note_id = 671744

    try:
        result = await general_notes(note_id)
        print(result)
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

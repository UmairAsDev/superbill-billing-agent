
import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from sqlalchemy import text
from database.deps import async_db_session
from loguru import logger
logger.add("logs/biopsy.log", rotation="10 MB")
from database.deps import async_db_session
from database.conn import async_engine



async def biopsy_notes(note_id: int):
    """Fetch biopsy notes for a given note ID."""
    async with async_db_session() as db:
        biopsy_query = text(
            """
        SELECT papb.noteId, pl.proName, papb.ruleOutDx, sl.site, sll.location, papb.lesionSize, papb.checkMargin, pml.`method`, pcl.cleansing, pal.anesthesia, pbl.blade,
        papb.undermining, papb.underminingSize, papb.woundSize, papb.closureSize, papb.intSuture, papb.intSutureSize, papb.extSuture, papb.extSutureSize,
        papb.dogEar, papb.dogEarCount, papb.flapClosure, pdl.dressing, papb.pathology, papb.pathRefPrefix, papb.pathRefNo, papb.frozenSection, papb.frozenRefPrefix,
        papb.frozenRefNo, papb.void, papb.cancel, papb.cancelBy, papb.cancelDetail, papb.notes, papb.lastModified, papb.delayedRepair, papb.marginOptions,
        papb.repairDate, papb.deleted
        FROM pnAssessmentProBiop papb
        LEFT JOIN proList pl ON pl.proId = papb.proId
        LEFT JOIN siteList sl ON sl.siteId = papb.siteId
        LEFT JOIN siteLocationList sll ON sll.locationId = papb.locationId
        LEFT JOIN proMethodList pml ON pml.methodId = papb.methodId
        LEFT JOIN proCleansingList pcl ON pcl.cleansingId = papb.cleansingId
        LEFT JOIN proAnesthesiaList pal ON pal.anesthesiaId = papb.anesthesiaId
        LEFT JOIN proBladeList pbl ON pbl.bladeId = papb.bladeId
        LEFT JOIN proDressingList pdl ON pdl.dressingId = papb.dressingId
            WHERE papb.noteId = :note_id
        """
        )
        result = await db.execute(biopsy_query, {"note_id": note_id})
        biopsy_notes = result.mappings().all()
        if not biopsy_notes:
            return []
        return [dict(row) for row in biopsy_notes]
    


async def main(note_id: int):
    try:
        result = await biopsy_notes(note_id)
        return result
    finally:
        await async_engine.dispose()





if __name__ == "__main__":
    test_note_id = 711231
    result = asyncio.run(main(test_note_id))
    print(result)
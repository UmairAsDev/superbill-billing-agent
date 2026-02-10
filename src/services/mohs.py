
import sys
import asyncio
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from sqlalchemy import text
from database.deps import async_db_session
from loguru import logger
logger.add("logs/mohs.log", rotation="10 MB")
from database.deps import async_db_session
from database.conn import async_engine




async def mohs_notes(note_id: int):
    """Fetch mohs notes for a given note ID."""
    async with async_db_session() as db:
        mohs_query = text(

        """
        SELECT 
        papm.noteId, pl.proName , papm.assessmentId, papm.mohsId, papm.drawingId, papm.providerId, papm.asprin, papm.coumadin, papm.plavix, papm.vitamine,
        papm.warfarin, sl.site, sll.location, papm.preOpSize, pcl.cleansing, pal.anesthesia, papm.preMohsNote, papm.postMohsSizeLinear, papm.curettage, papm.hPressure,
        papm.hCautery, papm.hLigation, papm.hGelfoam, papm.hPacking, papm.mohsNote, papm.postMohsSize, papm.refForRepair, papm.electroDessi, papm.refRepairTo, papm.repairId,
        papm.undermining, papm.underminingSize, papm.intSuture, papm.intSutureSize, papm.extSuture, papm.extSutureSize, papm.dogEarRepaired, papm.noOfDogEars, papm.flapClosure, papm.postRepairSize,
        papm.repairNote, papm.dSiteId, papm.dDefectSize, papm.dLocationId, papm.dRepairId, papm.dUndermining, papm.dIntSuture, papm.dIntSutureSize, papm.dExtSuture, papm.dExtSutureSize,
        papm.dDogEarRepaired, papm.dNoOfDogEars, papm.dFlapClosure, papm.dPostRepairSize, papm.dNote, papm.aquaGuard, papm.bacitracin, papm.bactroban, papm.dryGauze, papm.centany,
        papm.neosporin, papm.opSite, papm.telfa, papm.steriStrips, papm.vaseline, papm.xeroform, papm.pressDressing, papm.polysporin, papm.woundSeal, papm.noComplication,
        papm.bleeding, papm.pain, papm.hypotension, papm.otherComplication, papm.finalNote, papm.delayedRepair, papm.repairDetailId, papm.deleted
        FROM pnAssessmentProMohs papm
        LEFT JOIN proList pl ON pl.proId = papm.proId
        LEFT JOIN siteList sl ON sl.siteId = papm.siteId
        LEFT JOIN siteLocationList sll ON sll.locationId = papm.locationId
        LEFT JOIN proCleansingList pcl ON pcl.cleansingId = papm.cleansingId
        LEFT JOIN proAnesthesiaList pal ON pal.anesthesiaId = papm.anesthesiaId
            WHERE papm.noteId = :note_id
                """
        )
        result = await db.execute(mohs_query, {"note_id": note_id})
        mohs_notes = result.mappings().all()
        if not mohs_notes:
            return []
        return [dict(row) for row in mohs_notes]
    
    
async def main(note_id: int):
    try:
        result = await mohs_notes(note_id)
        return result
    finally:
        await async_engine.dispose()





if __name__ == "__main__":
    test_note_id = 703199
    result = asyncio.run(main(test_note_id))
    print(result)
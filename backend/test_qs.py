import asyncio
from app.db.database import AsyncSessionLocal
from sqlalchemy.future import select
from app.db.models import ResearchThread

async def run():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(ResearchThread).where(ResearchThread.agent_id == '8efc27e1-6a1d-4423-a258-5ab687e9a8fc'))
        threads = res.scalars().all()
        for t in threads:
            print(f'Thread {t.id}: last_activity_at = {t.last_activity_at}')

asyncio.run(run())


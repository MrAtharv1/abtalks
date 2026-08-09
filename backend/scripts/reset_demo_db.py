import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine

# Need to import all models to ensure Base knows about them
from app.db.database import Base
from app.db.models import *  # ensure all models are registered
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_demo_db")

async def reset_db():
    logger.warning("WARNING: This will completely destroy the local demo database.")
    logger.warning(f"Target DB URL: {settings.database_url}")
    
    if "sqlite" not in settings.database_url:
        logger.error("Refusing to drop a non-SQLite database to prevent production data loss.")
        return
        
    confirmation = input("Are you sure you want to drop all tables and recreate them? (y/N): ")
    if confirmation.lower() != 'y':
        logger.info("Aborted.")
        return

    engine = create_async_engine(settings.database_url, echo=False)
    
    async with engine.begin() as conn:
        logger.info("Dropping all existing tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Recreating all tables...")
        await conn.run_sync(Base.metadata.create_all)
        
    logger.info("Database reset successful.")

if __name__ == "__main__":
    asyncio.run(reset_db())

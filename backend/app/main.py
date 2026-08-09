from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.db.database import engine, Base
from app.db.migrations import run_migrations
from app.api.agent import router as agent_router
from app.api.dashboard import router as dashboard_router
from app.runtime.agent_runtime import runtime_manager
import logging

logger = logging.getLogger("thread")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Create new tables (does not alter existing ones)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Add missing columns to existing tables (idempotent)
    await run_migrations(engine)

    # 3. Recover active agents
    await runtime_manager.recover_active_agents()

    yield

    # Teardown: graceful shutdown
    await runtime_manager.shutdown_all()


app = FastAPI(
    title="THREAD - AI Persona API",
    description="Autonomous AI Persona",
    version="0.2.0",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for the hackathon (including Vercel domain)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(dashboard_router)


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.2.0"}

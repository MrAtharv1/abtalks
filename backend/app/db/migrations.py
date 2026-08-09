"""
Lightweight schema migration helper for THREAD.

SQLAlchemy's create_all() creates new tables but does NOT add new columns
to existing tables. This module runs ALTER TABLE statements to add missing
columns discovered at startup.

This is intentionally minimal — no Alembic dependency.
Each migration is idempotent (checks if column exists before adding).
"""
import logging

logger = logging.getLogger("thread")

# Each entry: (table, column, sqlite_type, default)
MIGRATIONS = [
    # Agent table — Phase 7 runtime stats
    ("agents", "last_post_at", "DATETIME", None),
    ("agents", "total_cycles", "INTEGER", "0"),
    ("agents", "total_posts", "INTEGER", "0"),
    ("agents", "total_llm_calls", "INTEGER", "0"),

    # ResearchQuestion — yield memory
    ("research_questions", "research_attempts", "INTEGER", "0"),
    ("research_questions", "successful_runs", "INTEGER", "0"),
    ("research_questions", "useful_evidence_count", "INTEGER", "0"),
    ("research_questions", "consecutive_low_yield_runs", "INTEGER", "0"),
    ("research_questions", "last_meaningful_change_at", "DATETIME", None),
    ("research_questions", "yield_score", "REAL", "0.5"),
    ("research_questions", "stagnant_until", "DATETIME", None),

    # ResearchRun — yield tracking
    ("research_runs", "yield_score", "REAL", None),
    ("research_runs", "source_diversity_score", "REAL", None),
    ("research_runs", "contradiction_count", "INTEGER", "0"),
    ("research_runs", "belief_change_delta", "REAL", None),

    # Source — freshness
    ("sources", "first_seen_at", "DATETIME", None),
    ("sources", "last_seen_at", "DATETIME", None),

    # AgentCycle — use INTEGER for counts
    # (existing rows used Float; new rows use Integer — SQLite handles both)
    # No migration needed; existing schema already works.
]


async def run_migrations(engine) -> None:
    """Run all pending schema migrations. Safe to call on every startup."""
    logger.info("[MIGRATION] Running schema migrations...")
    migrated = 0
    async with engine.begin() as conn:
        for table, column, col_type, default in MIGRATIONS:
            # Check if column already exists
            existing_cols = await conn.run_sync(
                lambda c, t=table: [
                    row[1] for row in c.execute(
                        __import__("sqlalchemy").text(f"PRAGMA table_info({t})")
                    ).fetchall()
                ]
            )
            if column not in existing_cols:
                default_clause = f" DEFAULT {default}" if default is not None else ""
                sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
                await conn.execute(__import__("sqlalchemy").text(sql))
                logger.info(f"[MIGRATION] Added column: {table}.{column}")
                migrated += 1

    if migrated == 0:
        logger.info("[MIGRATION] Schema is up to date.")
    else:
        logger.info(f"[MIGRATION] Applied {migrated} migration(s).")

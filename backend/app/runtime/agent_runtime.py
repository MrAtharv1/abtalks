"""
RuntimeManager — the central autonomous loop manager for THREAD agents.

Architecture:
    One asyncio.Task per agent.
    CadenceController drives timing (min/max interval, exponential backoff).
    LLMBudgetManager tracks and gates LLM spend per cycle and per hour.
    AgentRuntimeState provides explicit state machine transitions.
    ResearchOpportunityGate gates research decisions (no LLM calls).

Failure classification:
    ProviderQuotaExhausted  → BUDGET_EXHAUSTED backoff (max interval)
    asyncio.TimeoutError    → TRANSIENT backoff
    asyncio.CancelledError  → clean exit
    Exception               → TRANSIENT backoff

Singleton safety:
    RuntimeManager.start() checks active_tasks before creating a new task.
    Calling start() for an already-running agent is a no-op (logged as warning).

Shutdown safety:
    shutdown_all() cancels all tasks, waits for completion, clears registry.
"""
import asyncio
import logging

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Agent
from app.llm.provider import get_llm_provider, get_fast_llm_provider
from app.llm.provider import ProviderQuotaExhausted
from app.research.search import get_search_provider
from app.research.service import ResearchService
from app.memory.belief_engine import BeliefService
from app.editorial.service import EditorialService
from app.runtime.cycle import AgentCycleContext
from app.runtime.budget import LLMBudgetManager
from app.runtime.cadence import CadenceController
from app.runtime.state import runtime_state_registry
from sqlalchemy.future import select

logger = logging.getLogger("thread")


class RuntimeManager:
    def __init__(self):
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.stop_events: dict[str, asyncio.Event] = {}
        self.agent_locks: dict[str, asyncio.Lock] = {}
        self.agent_budgets: dict[str, LLMBudgetManager] = {}
        self.agent_cadences: dict[str, CadenceController] = {}

    def _get_lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self.agent_locks:
            self.agent_locks[agent_id] = asyncio.Lock()
        return self.agent_locks[agent_id]

    def _get_budget(self, agent_id: str) -> LLMBudgetManager:
        if agent_id not in self.agent_budgets:
            self.agent_budgets[agent_id] = LLMBudgetManager()
        return self.agent_budgets[agent_id]

    def _get_cadence(self, agent_id: str) -> CadenceController:
        if agent_id not in self.agent_cadences:
            self.agent_cadences[agent_id] = CadenceController()
        return self.agent_cadences[agent_id]

    async def _agent_loop(self, agent_id: str, stop_event: asyncio.Event):
        logger.info(f"[RUNTIME] runtime_started agent_id={agent_id}")
        lock = self._get_lock(agent_id)
        budget = self._get_budget(agent_id)
        cadence = self._get_cadence(agent_id)
        state = runtime_state_registry.get_or_create(agent_id)
        state.transition("STARTING")

        # Initial delay (0 in evaluator mode / default)
        if settings.runtime_initial_delay_seconds > 0:
            logger.info(
                f"[RUNTIME] initial_delay seconds={settings.runtime_initial_delay_seconds} "
                f"agent_id={agent_id}"
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=settings.runtime_initial_delay_seconds)
                if stop_event.is_set():
                    logger.info(f"[RUNTIME] runtime_stopped agent_id={agent_id} reason=cancelled")
                    state.force_transition("STOPPED")
                    return
            except asyncio.TimeoutError:
                pass

        while not stop_event.is_set():
            # Wait for cadence to allow next cycle
            if not cadence.is_cycle_allowed():
                wait_seconds = cadence.seconds_until_next_cycle()
                current_state = "COOLDOWN" if cadence.consecutive_failures == 0 else "BACKOFF"
                state.force_transition(current_state)
                logger.info(
                    f"[RUNTIME] cycle_cooldown agent_id={agent_id} "
                    f"seconds={wait_seconds:.1f} state={current_state}"
                )
                await cadence.wait_for_next_cycle(stop_event)
                if stop_event.is_set():
                    break

            try:
                async with lock:
                    state.transition("RUNNING")
                    state.record_cycle_start()
                    cadence.record_cycle_start()

                    # Reset per-cycle budget
                    await budget.reset_cycle()

                    async with AsyncSessionLocal() as db:
                        llm = get_llm_provider()
                        fast_llm = get_fast_llm_provider()
                        search_provider = get_search_provider()

                        research_svc = ResearchService(
                            db, llm, search_provider, fast_llm_provider=fast_llm
                        )
                        belief_svc = BeliefService(db, llm)
                        editorial_svc = EditorialService(db, llm)

                        ctx = AgentCycleContext(
                            db=db,
                            research_service=research_svc,
                            belief_service=belief_svc,
                            editorial_service=editorial_svc,
                            budget_manager=budget,
                            runtime_state=state,
                        )

                        await asyncio.wait_for(
                            ctx.run_cycle(agent_id, stop_event),
                            timeout=settings.cycle_timeout
                        )

                # Cycle completed successfully
                state.record_cycle_success()
                cadence.record_success()
                state.transition("COOLDOWN")

                logger.info(
                    f"[RUNTIME] cycle_completed agent_id={agent_id} "
                    f"budget={budget.remaining_budget()['cycle_calls_used']}/"
                    f"{settings.max_llm_calls_per_cycle} calls"
                )

            except asyncio.TimeoutError:
                logger.error(f"[RUNTIME] cycle_timeout agent_id={agent_id}")
                state.record_cycle_failure()
                cadence.record_failure("TRANSIENT")
                state.force_transition("BACKOFF")

            except asyncio.CancelledError:
                logger.info(f"[RUNTIME] runtime_stopped agent_id={agent_id} reason=cancelled")
                state.force_transition("STOPPING")
                state.force_transition("STOPPED")
                break

            except ProviderQuotaExhausted as e:
                logger.warning(
                    f"[RUNTIME] budget_exhausted agent_id={agent_id}: {e}"
                )
                state.record_cycle_failure()
                state.record_429()
                cadence.record_failure("BUDGET_EXHAUSTED")
                state.force_transition("BUDGET_EXHAUSTED")

            except Exception as e:
                logger.error(
                    f"[RUNTIME] cycle_failed agent_id={agent_id}: {type(e).__name__}: {e}"
                )
                state.record_cycle_failure()
                cadence.record_failure("TRANSIENT")
                state.force_transition("BACKOFF")
                
        logger.info(f"[RUNTIME] finalizing agent_id={agent_id}")
        state.force_transition("STOPPING")
        state.force_transition("STOPPED")

    def start(self, agent_id: str) -> bool:
        """Start the runtime loop for an agent. Singleton-safe."""
        if agent_id in self.active_tasks and not self.active_tasks[agent_id].done():
            logger.warning(
                f"[RUNTIME] Runtime for agent {agent_id} is already running. Ignoring duplicate start."
            )
            return False

        if not settings.runtime_enabled:
            logger.info(f"[RUNTIME] runtime_disabled, skipping start for agent {agent_id}")
            return False

        self.stop_events[agent_id] = asyncio.Event()
        task = asyncio.create_task(self._agent_loop(agent_id, self.stop_events[agent_id]))
        self.active_tasks[agent_id] = task
        logger.info(f"[RUNTIME] Started runtime task for agent {agent_id}")
        return True

    def stop(self, agent_id: str):
        """Legacy stop: abruptly cancel the runtime loop."""
        if agent_id in self.active_tasks:
            self.active_tasks[agent_id].cancel()
            del self.active_tasks[agent_id]
            self.stop_events.pop(agent_id, None)
            logger.info(f"[RUNTIME] Stopped runtime task for agent {agent_id}")

    async def stop_and_wait(self, agent_id: str, timeout: float = 15.0):
        """Cooperatively stop the runtime and wait for it to exit."""
        if agent_id in self.active_tasks:
            logger.info(f"[RUNTIME] cancellation_started agent_id={agent_id}")
            if agent_id in self.stop_events:
                self.stop_events[agent_id].set()
            task = self.active_tasks[agent_id]
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
                logger.info(f"[RUNTIME] cancellation_observed agent_id={agent_id}")
            except asyncio.TimeoutError:
                logger.warning(f"[RUNTIME] cancellation_timeout agent_id={agent_id}, forcing task.cancel()")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self.active_tasks.pop(agent_id, None)
            self.stop_events.pop(agent_id, None)
            logger.info(f"[RUNTIME] stopped agent_id={agent_id}")

    async def recover_active_agents(self):
        """Recover any ACTIVE agents from the database on startup."""
        logger.info("Recovering active agents from database...")
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Agent).where(Agent.status == "ACTIVE"))
            agents = result.scalars().all()
            for agent in agents:
                self.start(agent.id)

    async def shutdown_all(self):
        """Graceful shutdown of all runtime loops."""
        logger.info(f"[RUNTIME] Shutting down all agent runtimes ({len(self.active_tasks)} tasks)...")
        tasks = list(self.active_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.active_tasks.clear()
        logger.info("[RUNTIME] runtime_stopped all agents")

    def get_agent_status(self, agent_id: str) -> dict:
        """Return runtime status for an agent (for the dashboard endpoint)."""
        state = runtime_state_registry.get(agent_id)
        budget = self.agent_budgets.get(agent_id)
        cadence = self.agent_cadences.get(agent_id)

        if state is None:
            return {"state": "STOPPED", "agent_id": agent_id}

        return state.dashboard(
            budget_snapshot=budget.remaining_budget() if budget else {},
            cadence_snapshot=cadence.state_snapshot() if cadence else {},
        )


runtime_manager = RuntimeManager()

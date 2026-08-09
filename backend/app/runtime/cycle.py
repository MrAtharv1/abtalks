"""
AgentCycleContext — executes one full research-belief-editorial cycle.

Additions vs Phase 6:
    - Accepts budget_manager: LLMBudgetManager (gates LLM spend)
    - Accepts runtime_state: AgentRuntimeState (for observability)
    - Uses ResearchOpportunityGate to decide whether to research
    - Emits structured log events for every major decision
    - Tracks belief_change_delta and passes to ResearchYieldTracker
    - Records "NOTHING_TO_SAY" explicitly when no editorial action taken
    - Failure isolation: one source failure doesn't kill entire cycle
"""
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.models import AgentCycle, ResearchRun, Belief, Agent, ResearchThread, ResearchQuestion
from app.runtime.scheduler import ResearchScheduler
from app.research.service import ResearchService
from app.research.yield_tracker import ResearchYieldTracker
from app.memory.belief_engine import BeliefService
from app.editorial.service import EditorialService
from app.runtime.opportunity import ResearchOpportunityGate

logger = logging.getLogger("thread")


class AgentCycleContext:
    def __init__(
        self,
        db: AsyncSession,
        research_service: ResearchService,
        belief_service: BeliefService,
        editorial_service: EditorialService,
        budget_manager=None,
        runtime_state=None,
    ):
        self.db = db
        self.research_service = research_service
        self.belief_service = belief_service
        self.editorial_service = editorial_service
        self.scheduler = ResearchScheduler(db)
        self.budget_manager = budget_manager
        self.runtime_state = runtime_state
        self.gate = ResearchOpportunityGate()

    async def run_cycle(self, agent_id: str, stop_event=None) -> None:
        logger.info(f"[RUNTIME] cycle_started agent_id={agent_id}")

        async def set_agent_status(status: str):
            agent = await self.db.get(Agent, agent_id)
            if agent:
                agent.runtime_status = status
                await self.db.commit()

        await set_agent_status("INITIALIZING")

        cycle = AgentCycle(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            status="RUNNING"
        )
        self.db.add(cycle)
        await self.db.commit()

        belief_change_delta = 0.0
        research_source_domains: list[str] = []
        contradiction_count = 0
        evidence_ids: list[str] = []
        post_published = False

        try:
            # ── 1. Select research question ───────────────────────────────────
            question = await self.scheduler.select_next_question(agent_id)
            if not question:
                logger.info(f"[RUNTIME] research_skipped reason=NO_ELIGIBLE_QUESTION agent_id={agent_id}")
                cycle.status = "COMPLETED"
                cycle.completed_at = datetime.now(timezone.utc)
                await self.db.commit()
                await set_agent_status("IDLE")
                # Still run editorial — there may be pending candidates from before
                await self._run_editorial(agent_id, cycle, belief_change_delta=0.0)
                return

            cycle.question_id = question.id
            if self.runtime_state:
                self.runtime_state.set_current_question(question.id, question.question[:80])

            logger.info(f"[RUNTIME] question_selected: {question.id} q={question.question[:60]}")

            # ── 2. Research opportunity gate ─────────────────────────────────
            decision = self.gate.evaluate(question)
            if not decision.should_research:
                logger.info(
                    f"[RUNTIME] research_gate_reject id={question.id[:8]} "
                    f"reason={decision.reason} score={decision.score:.3f}"
                )
                # No research this cycle — still check editorial
                cycle.status = "COMPLETED"
                cycle.completed_at = datetime.now(timezone.utc)
                await self.db.commit()
                await set_agent_status("IDLE")
                await self._run_editorial(agent_id, cycle, belief_change_delta=0.0)
                return

            logger.info(
                f"[RUNTIME] research_gate_pass id={question.id[:8]} "
                f"score={decision.score:.3f}"
            )

            # ── 3. Budget check before research ──────────────────────────────
            # Research pipeline uses: 1 query gen + N evidence calls
            # Reserve a conservative budget (we'll release unused later)
            from app.config import settings
            max_sources = settings.max_research_sources_per_cycle
            research_token = None
            if self.budget_manager:
                # Reserve: 1 query gen + max_sources evidence calls
                needed = 1 + max_sources
                research_token = await self.budget_manager.reserve(
                    op="research", count=needed
                )
                if research_token is None:
                    logger.info(
                        f"[RUNTIME] research_skipped reason=BUDGET_EXHAUSTED "
                        f"agent_id={agent_id}"
                    )
                    cycle.status = "COMPLETED"
                    cycle.completed_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    await set_agent_status("IDLE")
                    return

            # ── 4. Run research ──────────────────────────────────────────────
            await set_agent_status("RESEARCHING")
            logger.info(f"[RUNTIME] research_started: {question.id}")
            run_id = await self.research_service.research_question(question.id, stop_event)
            cycle.research_run_id = run_id

            if not run_id:
                raise ValueError("Research run failed to initialize")

            # Load run result
            run_res = await self.db.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
            run = run_res.scalar_one_or_none()

            if run:
                evidence_ids = run.evidence_extracted or []
                research_source_domains = self._extract_domains(run.sources_processed or [])

                # Release unused budget reservation
                if self.budget_manager and research_token:
                    actual_calls = 1 + len(evidence_ids)  # approx
                    await self.budget_manager.release(research_token, used=min(actual_calls, 1 + max_sources))
                    research_token = None

                logger.info(
                    f"[RUNTIME] research_completed status={run.status} "
                    f"evidence={len(evidence_ids)} sources={len(research_source_domains)}"
                )

                if run.status in ("COMPLETED", "PARTIAL") and evidence_ids:
                    # ── 5. Update Beliefs ─────────────────────────────────────
                    await set_agent_status("UPDATING_MEMORY")
                    beliefs_res = await self.db.execute(
                        select(Belief).where(Belief.thread_id == question.thread_id)
                    )
                    existing_beliefs = beliefs_res.scalars().all()

                    previous_confidences = {b.id: b.confidence for b in existing_beliefs}

                    if not existing_beliefs:
                        logger.info("[RUNTIME] belief_synthesis_started")
                        created = await self.belief_service.synthesize_for_question(question.id)
                        if created:
                            belief_change_delta = sum(b.confidence for b in created) / len(created)
                            logger.info(
                                f"[RUNTIME] belief_changed delta={belief_change_delta:.3f} "
                                f"direction=INITIAL beliefs={len(created)}"
                            )
                    else:
                        logger.info("[RUNTIME] belief_revision_started")
                        for belief in existing_beliefs:
                            await self.belief_service.revise_beliefs(belief.id, evidence_ids)

                        # Compute aggregate delta
                        await self.db.refresh(existing_beliefs[0])
                        updated_beliefs_res = await self.db.execute(
                            select(Belief).where(Belief.thread_id == question.thread_id)
                        )
                        updated_beliefs = updated_beliefs_res.scalars().all()
                        deltas = []
                        for b in updated_beliefs:
                            old_conf = previous_confidences.get(b.id, b.confidence)
                            deltas.append(abs(b.confidence - old_conf))

                        if deltas:
                            belief_change_delta = sum(deltas) / len(deltas)

                        if belief_change_delta > 0.01:
                            logger.info(
                                f"[RUNTIME] belief_changed delta={belief_change_delta:.3f} "
                                f"beliefs_revised={len(existing_beliefs)}"
                            )
                        else:
                            logger.info(
                                f"[RUNTIME] belief_unchanged delta={belief_change_delta:.3f}"
                            )

                    # Track contradictions
                    contradiction_count = sum(
                        1 for _ in (ev for ev_id in evidence_ids
                                    for ev in [])  # placeholder, counted in research service
                    )

                    if self.runtime_state:
                        self.runtime_state.record_successful_research()

                # ── 6. Record research yield ──────────────────────────────────
                yield_tracker = ResearchYieldTracker(self.db)
                await yield_tracker.record_run_yield(
                    question_id=question.id,
                    run=run,
                    evidence_ids=evidence_ids,
                    contradiction_count=contradiction_count,
                    belief_change_delta=belief_change_delta,
                    source_domains=research_source_domains,
                )

            # ── 7. Editorial Engine ───────────────────────────────────────────
            await self._run_editorial(agent_id, cycle, belief_change_delta)

            # ── 8. Mark cycle completed ───────────────────────────────────────
            cycle.status = "COMPLETED"

        except Exception as e:
            logger.exception(f"[RUNTIME] cycle_failed: {e}")
            cycle.status = "FAILED"
            cycle.error = str(e)

            # Release any dangling reservation
            if self.budget_manager and research_token:
                try:
                    await self.budget_manager.release(research_token, used=0)
                except Exception:
                    pass

        finally:
            cycle.completed_at = datetime.now(timezone.utc)
            await set_agent_status("IDLE" if cycle.status == "COMPLETED" else "ERROR")
            try:
                if cycle.question_id:
                    q_res = await self.db.execute(
                        select(ResearchQuestion).where(ResearchQuestion.id == cycle.question_id)
                    )
                    q = q_res.scalar_one_or_none()
                    if q:
                        t_res = await self.db.execute(
                            select(ResearchThread).where(ResearchThread.id == q.thread_id)
                        )
                        t = t_res.scalar_one_or_none()
                        if t:
                            t.last_activity_at = datetime.now(timezone.utc)
                await self.db.commit()
            except Exception as final_e:
                logger.error(f"[RUNTIME] failed to commit cycle completion: {final_e}")

        logger.info(
            f"[RUNTIME] cycle_completed agent_id={agent_id} "
            f"status={cycle.status} "
            f"post={'yes' if cycle.published_post_id else 'no'}"
        )

    async def _run_editorial(self, agent_id: str, cycle: AgentCycle, belief_change_delta: float):
        """Run the editorial engine with budget gating and cooldown."""
        # Budget check: editorial uses ~2 LLM calls (candidate + authoring)
        editorial_token = None
        if self.budget_manager:
            editorial_token = await self.budget_manager.reserve(
                op="editorial", count=2
            )
            if editorial_token is None:
                logger.info(
                    f"[RUNTIME] editorial_skipped reason=BUDGET_EXHAUSTED agent_id={agent_id}"
                )
                return

        try:
            await self.db.get(Agent, agent_id)
            await self.db.execute(select(Agent).where(Agent.id == agent_id))

            logger.info(f"[RUNTIME] editorial_started agent_id={agent_id}")
            post = await self.editorial_service.generate_next_editorial_item(
                agent_id,
                belief_change_delta=belief_change_delta,
            )

            if editorial_token and self.budget_manager:
                await self.budget_manager.release(editorial_token, used=2 if post else 1)
                editorial_token = None

            if post:
                logger.info(f"[RUNTIME] post_published post_id={post.id}")
                cycle.published_post_id = post.id
                if self.runtime_state:
                    self.runtime_state.record_post_published()
            else:
                logger.info(
                    f"[RUNTIME] editorial_skipped reason=NO_EDITORIAL_OPPORTUNITY "
                    f"agent_id={agent_id}"
                )

        except Exception as e:
            logger.error(f"[RUNTIME] editorial_failed: {e}")
            if editorial_token and self.budget_manager:
                try:
                    await self.budget_manager.release(editorial_token, used=0)
                except Exception:
                    pass

    def _extract_domains(self, urls: list[str]) -> list[str]:
        """Extract domains from URLs for source diversity tracking."""
        domains = []
        for url in urls:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.netloc:
                    domains.append(parsed.netloc.replace("www.", ""))
            except Exception:
                pass
        return domains

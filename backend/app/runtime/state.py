"""
RuntimeStateMachine — explicit per-agent runtime state tracking.

States:
    STOPPED          — agent not running
    STARTING         — agent loop initializing
    RUNNING          — actively executing a cycle
    COOLDOWN         — between cycles (normal cadence)
    BACKOFF          — recovering from transient failure
    BUDGET_EXHAUSTED — provider quota exhausted, waiting for reset
    STOPPING         — graceful shutdown in progress
    FAILED           — unrecoverable error (permanent failure)

States are in-process (not persisted). On restart, agents recover to STARTING.
The Agent.runtime_status in the DB is a simplified version for persistence.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

logger = logging.getLogger("thread")

RuntimeState = Literal[
    "STOPPED", "STARTING", "RUNNING", "COOLDOWN", "BACKOFF",
    "BUDGET_EXHAUSTED", "STOPPING", "FAILED"
]

# Valid transitions
VALID_TRANSITIONS: dict[RuntimeState, set[RuntimeState]] = {
    "STOPPED":          {"STARTING"},
    "STARTING":         {"RUNNING", "FAILED", "STOPPING"},
    "RUNNING":          {"COOLDOWN", "BACKOFF", "BUDGET_EXHAUSTED", "FAILED", "STOPPING"},
    "COOLDOWN":         {"RUNNING", "STOPPING"},
    "BACKOFF":          {"RUNNING", "STOPPING", "FAILED"},
    "BUDGET_EXHAUSTED": {"RUNNING", "STOPPING", "FAILED"},
    "FAILED":           {"STARTING", "STOPPING"},
    "STOPPING":         {"STOPPED"},
}


@dataclass
class RuntimeStats:
    """Lifetime stats for an agent's runtime."""
    cycles_completed: int = 0
    cycles_failed: int = 0
    posts_created: int = 0
    llm_calls_total: int = 0
    rate_limit_429_total: int = 0
    consecutive_failures: int = 0
    last_cycle_at: Optional[datetime] = None
    last_post_at: Optional[datetime] = None
    last_successful_research_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    current_question_id: Optional[str] = None
    current_question_text: Optional[str] = None


class AgentRuntimeState:
    """
    State machine for a single agent's runtime lifecycle.
    Not thread-safe by itself — caller must use asyncio.Lock.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self._state: RuntimeState = "STOPPED"
        self._stats = RuntimeStats()

    @property
    def state(self) -> RuntimeState:
        return self._state

    def transition(self, new_state: RuntimeState) -> bool:
        """
        Attempt to transition to a new state.
        Returns True if transition was valid and applied.
        """
        allowed = VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            logger.warning(
                f"[STATE] Invalid transition for agent {self.agent_id}: "
                f"{self._state} → {new_state}"
            )
            return False
        logger.debug(f"[STATE] agent={self.agent_id} {self._state} → {new_state}")
        self._state = new_state
        return True

    def force_transition(self, new_state: RuntimeState):
        """Force a transition regardless of validity (use for cleanup/shutdown)."""
        logger.debug(f"[STATE] agent={self.agent_id} FORCE {self._state} → {new_state}")
        self._state = new_state

    def record_cycle_start(self):
        self._stats.last_cycle_at = datetime.now(timezone.utc)
        if not self._stats.started_at:
            self._stats.started_at = self._stats.last_cycle_at

    def record_cycle_success(self):
        self._stats.cycles_completed += 1
        self._stats.consecutive_failures = 0

    def record_cycle_failure(self):
        self._stats.cycles_failed += 1
        self._stats.consecutive_failures += 1

    def record_post_published(self):
        self._stats.posts_created += 1
        self._stats.last_post_at = datetime.now(timezone.utc)

    def record_successful_research(self):
        self._stats.last_successful_research_at = datetime.now(timezone.utc)

    def record_429(self):
        self._stats.rate_limit_429_total += 1

    def set_current_question(self, question_id: Optional[str], question_text: Optional[str] = None):
        self._stats.current_question_id = question_id
        self._stats.current_question_text = question_text

    def dashboard(self, budget_snapshot: dict | None = None, cadence_snapshot: dict | None = None) -> dict:
        """Returns full observability dashboard for this agent."""
        return {
            "agent_id": self.agent_id,
            "state": self._state,
            "cycles_completed": self._stats.cycles_completed,
            "cycles_failed": self._stats.cycles_failed,
            "consecutive_failures": self._stats.consecutive_failures,
            "posts_created": self._stats.posts_created,
            "started_at": self._stats.started_at.isoformat() if self._stats.started_at else None,
            "last_cycle_at": self._stats.last_cycle_at.isoformat() if self._stats.last_cycle_at else None,
            "last_post_at": self._stats.last_post_at.isoformat() if self._stats.last_post_at else None,
            "last_successful_research_at": (
                self._stats.last_successful_research_at.isoformat()
                if self._stats.last_successful_research_at else None
            ),
            "current_question_id": self._stats.current_question_id,
            "current_question_text": self._stats.current_question_text,
            "budget": budget_snapshot or {},
            "cadence": cadence_snapshot or {},
        }


class RuntimeStateRegistry:
    """
    In-process registry of per-agent runtime state machines.
    Singleton — one instance per server process.
    """

    def __init__(self):
        self._agents: dict[str, AgentRuntimeState] = {}

    def get_or_create(self, agent_id: str) -> AgentRuntimeState:
        if agent_id not in self._agents:
            self._agents[agent_id] = AgentRuntimeState(agent_id)
        return self._agents[agent_id]

    def get(self, agent_id: str) -> AgentRuntimeState | None:
        return self._agents.get(agent_id)

    def remove(self, agent_id: str):
        self._agents.pop(agent_id, None)

    def all_states(self) -> dict[str, str]:
        return {aid: asm.state for aid, asm in self._agents.items()}


# Singleton registry
runtime_state_registry = RuntimeStateRegistry()

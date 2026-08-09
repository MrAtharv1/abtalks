from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # --- LLM Provider ---
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "llama-3.3-70b-versatile"
    # Fast model for high-volume ops (query gen, evidence extraction).
    # Defaults to llm_model if not set.
    llm_model_fast: str = ""
    llm_tpm_limit: int = 5000

    # Optional HuggingFace fallback (activates WithFallbackLLMProvider if set)
    llm_fallback_provider: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = ""
    llm_fallback_base_url: str = "https://router.huggingface.co/v1/chat/completions"

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./thread.db"

    # --- Search ---
    search_provider: str = "tavily"
    search_api_key: str = ""

    # --- Runtime Cadence ---
    runtime_enabled: bool = True
    runtime_initial_delay_seconds: int = 0      # First cycle starts immediately
    runtime_min_cycle_interval_seconds: int = 300   # 5 min minimum between cycles
    runtime_max_cycle_interval_seconds: int = 1800  # 30 min maximum (backoff cap)

    # --- Budget Control ---
    max_llm_calls_per_cycle: int = 8
    max_llm_calls_per_hour: int = 30
    max_research_sources_per_cycle: int = 5
    max_search_queries_per_cycle: int = 4

    # --- Legacy / kept for compatibility ---
    agent_cycle_interval_seconds: int = 300     # Alias for runtime_min_cycle_interval_seconds
    research_cooldown_seconds: int = 60
    max_cycles: int = 1000
    cycle_timeout: int = 600
    max_queries_per_cycle: int = 4
    max_sources_per_run: int = 5

    # --- Editorial Pacing ---
    editorial_min_interval_seconds: int = 180   # 3 min minimum between posts
    editorial_major_change_threshold: float = 0.3  # Belief delta that bypasses cooldown
    editorial_significance_threshold: float = 0.3  # Minimum score to publish

    # --- Research Intelligence ---
    research_stagnation_threshold: int = 3       # Consecutive low-yield runs → STAGNANT
    research_stagnation_cooldown_seconds: int = 3600  # 1 hour
    research_yield_low_threshold: float = 0.2    # Below this = low yield run
    research_contradiction_bonus: float = 0.3    # Extra scheduler weight for contradiction-seeking

    # --- Evaluator Mode ---
    # Tunes parameters for judging without bypassing autonomous architecture
    evaluator_mode: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def effective_fast_model(self) -> str:
        """Returns the fast model if configured, else falls back to the main model."""
        return self.llm_model_fast if self.llm_model_fast else self.llm_model

    @property
    def effective_min_cycle_interval(self) -> int:
        """Returns min cycle interval, adjusted for evaluator mode."""
        if self.evaluator_mode:
            return 60  # 1 minute in evaluator mode
        return self.runtime_min_cycle_interval_seconds

    @property
    def effective_editorial_min_interval(self) -> int:
        """Returns editorial interval, adjusted for evaluator mode."""
        if self.evaluator_mode:
            return 60
        return self.editorial_min_interval_seconds


settings = Settings()

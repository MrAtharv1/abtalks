"""
LLM Provider implementations for THREAD.

Provider hierarchy:
  get_llm_provider()        -> DefaultLLMProvider (Groq, strong model) optionally
                               wrapped in WithFallbackLLMProvider if HF fallback configured
  get_fast_llm_provider()   -> DefaultLLMProvider (Groq, fast model) for high-volume ops
                               (query generation, evidence extraction)

Rate-limit handling:
  TPM (tokens per minute): bounded retry with retry-after backoff, max 2 retries
  TPD (tokens per day):    raises ProviderQuotaExhausted immediately, no retry
  Fallback:                WithFallbackLLMProvider catches ProviderQuotaExhausted
                           from primary and delegates to HuggingFaceLLMProvider
"""
import asyncio
import json
import logging
import re
from typing import Type, TypeVar

from pydantic import BaseModel

from app.llm.base import LLMProvider
from app.config import settings
from app.llm.limiter import global_limiter

logger = logging.getLogger("thread")

T = TypeVar('T', bound=BaseModel)


class ProviderQuotaExhausted(Exception):
    """
    Raised when a provider has exhausted its daily quota (TPD limit).
    Should NOT be retried against the same provider/model.
    """
    pass


def _parse_retry_after_seconds(error_message: str) -> float:
    """
    Extract the retry-after seconds from a Groq 429 error message.
    Examples: "Please try again in 5.215s", "Please try again in 13m49.44s"
    Returns 0.0 if not parseable (caller handles default).
    """
    # Match patterns like "13m49.44s" or "5.215s"
    match = re.search(r'try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s', error_message)
    if match:
        minutes = float(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return minutes * 60 + seconds
    return 0.0


def _classify_429(response_text: str) -> str:
    """
    Classify a Groq 429 as 'tpm' or 'tpd'.
    Returns 'tpd' if the error mentions 'tokens per day', else 'tpm'.
    """
    try:
        error_body = json.loads(response_text)
        message = error_body.get("error", {}).get("message", "").lower()
    except Exception:
        message = response_text.lower()

    if "tokens per day" in message or "per day" in message or "tpd" in message:
        return "tpd"
    return "tpm"


class DefaultLLMProvider:
    """
    Primary LLM provider using Groq's OpenAI-compatible API.

    Args:
        model: Override the model from settings. If None, uses settings.llm_model.
    """

    def __init__(self, model: str | None = None):
        self._model = model

    def _effective_model(self) -> str:
        return self._model if self._model else settings.llm_model

    async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        if not settings.llm_api_key or settings.llm_api_key == "your_groq_api_key_here":
            raise ValueError("No LLM API key provided. Cannot generate structured output.")

        import httpx

        json_schema = schema.model_json_schema()

        system_prompt = (
            "You are a structured data extraction AI.\n"
            "You must generate a valid JSON object containing real data that conforms to the schema below.\n"
            "DO NOT output the JSON schema itself. Output only an instance of data that validates against the schema.\n"
            f"Schema: {json.dumps(json_schema)}\n"
            "IMPORTANT: All numeric values (floats like 0.9) MUST be JSON numbers, never spelled-out words."
        )

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json"
        }

        # Truncate large prompts to stay within context window limits.
        # 2000 chars keeps evidence extraction prompts reasonable while
        # preserving enough content for accurate extraction.
        truncated_prompt = prompt[:2000] if len(prompt) > 2000 else prompt

        model = self._effective_model()

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncated_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 1500
        }

        max_tpm_retries = 2
        tpm_retry_count = 0
        json_retry_count = 0
        
        # Estimate tokens (approx 4 chars per token for input, plus max_tokens for output)
        estimated_tokens = int(len(truncated_prompt) / 4) + 1500

        while True:
            await global_limiter.acquire(estimated_tokens)
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload
                    )
                
                # If we get a 200, we'll reconcile tokens after parsing
                if response.status_code == 200:
                    data = response.json()
                    actual_tokens = data.get("usage", {}).get("total_tokens", estimated_tokens)
                    await global_limiter.release(estimated_tokens, actual_tokens)
                else:
                    # For errors, we just release with the estimated cost since we didn't get usage stats
                    await global_limiter.release(estimated_tokens, estimated_tokens)
                    
            except Exception:
                global_limiter.release_on_exception()
                raise

            if response.status_code == 400 and "json_validate_failed" in response.text:
                if json_retry_count < max_tpm_retries:
                    json_retry_count += 1
                    logger.warning(
                        f"[LLM] Groq json_validate_failed for model '{model}'. "
                        f"Retry {json_retry_count}/{max_tpm_retries} after 1.0s. "
                        f"Details: {response.text[:200]}"
                    )
                    await asyncio.sleep(1.0)
                    continue
                else:
                    logger.error(
                        f"[LLM] Groq json_validate_failed exceeded after {max_tpm_retries} retries for model '{model}'."
                    )
                    raise Exception(
                        f"Groq json_validate_failed after {max_tpm_retries} retries. "
                        f"Original error: {response.text}"
                    )

            if response.status_code == 429:
                rate_type = _classify_429(response.text)

                if rate_type == "tpd":
                    # Daily quota exhausted — do NOT retry this provider/model.
                    logger.warning(
                        f"[LLM] Groq TPD quota exhausted for model '{model}'. "
                        f"Raising ProviderQuotaExhausted. Details: {response.text[:200]}"
                    )
                    raise ProviderQuotaExhausted(
                        f"Groq daily quota (TPD) exhausted for model '{model}'. "
                        f"Original error: {response.text}"
                    )

                # TPM: handle with limiter backoff instead of immediate fallback
                retry_after = _parse_retry_after_seconds(response.text) or 5.0
                await global_limiter.handle_429(retry_after)
                
                if tpm_retry_count < max_tpm_retries:
                    tpm_retry_count += 1
                    logger.warning(
                        f"[LLM] primary_rate_limited provider=groq model='{model}'. "
                        f"Retry {tpm_retry_count}/{max_tpm_retries}. "
                        f"Details: {response.text[:200]}"
                    )
                    continue
                else:
                    logger.warning(
                        f"[LLM] primary_rate_limited provider=groq model='{model}'. "
                        f"Switching to fallback after {max_tpm_retries} retries."
                    )
                    raise ProviderQuotaExhausted(
                        f"Groq TPM rate limit exceeded for model '{model}'. "
                        f"Original error: {response.text}"
                    )

            if response.status_code != 200:
                raise Exception(f"Groq API Error {response.status_code}: {response.text}")

            data = response.json()
            if "choices" not in data or not data["choices"]:
                raise Exception("Malformed response from Groq API (missing 'choices').")

            message_content = data["choices"][0]["message"].get("content")
            if not message_content:
                raise Exception("Groq API returned empty content.")

            try:
                parsed_json = json.loads(message_content)
                logger.debug("[LLM] provider_capability_normalized primary=groq structured_output=native")
                return schema.model_validate(parsed_json)
            except Exception as e:
                raise Exception(
                    f"Failed to parse or validate JSON response from Groq: {e}\n"
                    f"Response: {message_content}"
                )


class HuggingFaceLLMProvider:
    """
    Fallback LLM provider using HuggingFace's Inference API
    (OpenAI-compatible endpoint).

    Used only when Groq raises ProviderQuotaExhausted.
    """

    def __init__(self, model: str | None = None):
        self._model = model

    def _effective_model(self) -> str:
        return self._model if self._model else settings.llm_fallback_model

    async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        api_key = settings.llm_fallback_api_key
        if not api_key:
            raise ProviderQuotaExhausted(
                "HuggingFace fallback is not configured (no LLM_FALLBACK_API_KEY)."
            )

        import httpx

        json_schema = schema.model_json_schema()

        system_prompt = (
            "You are a structured data extraction AI.\n"
            "You must generate a valid JSON object containing real data that conforms to the schema below.\n"
            "DO NOT output the JSON schema itself. Output only an instance of data that validates against the schema.\n"
            f"Schema: {json.dumps(json_schema)}\n"
            "IMPORTANT: All numeric values (floats like 0.9) MUST be JSON numbers, never spelled-out words."
        )

        truncated_prompt = prompt[:2000] if len(prompt) > 2000 else prompt
        model = self._effective_model()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": truncated_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 1500
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                settings.llm_fallback_base_url,
                headers=headers,
                json=payload
            )

        if response.status_code == 429:
            logger.warning(f"[LLM] HuggingFace rate limit hit for model '{model}'.")
            raise ProviderQuotaExhausted(
                f"HuggingFace rate limit exceeded for model '{model}'. "
                f"Original error: {response.text}"
            )

        if response.status_code != 200:
            raise Exception(f"HuggingFace API Error {response.status_code}: {response.text}")

        data = response.json()
        if "choices" not in data or not data["choices"]:
            raise Exception("Malformed response from HuggingFace API (missing 'choices').")

        message_content = data["choices"][0]["message"].get("content")
        if not message_content:
            raise Exception("HuggingFace API returned empty content.")

        try:
            parsed_json = json.loads(message_content)
            logger.debug("[LLM] provider_capability_normalized fallback=huggingface structured_output=prompted")
            return schema.model_validate(parsed_json)
        except Exception as e:
            raise Exception(
                f"Failed to parse or validate JSON response from HuggingFace: {e}\n"
                f"Response: {message_content}"
            )


class WithFallbackLLMProvider:
    """
    Thin decorator that wraps a primary LLMProvider with a fallback.
    
    On ProviderQuotaExhausted from the primary, delegates to the fallback.
    On any other error from the primary, propagates immediately.
    Architecture is preserved: all callers see the same LLMProvider interface.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self._primary = primary
        self._fallback = fallback

    async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        try:
            return await self._primary.generate_structured(prompt, schema)
        except ProviderQuotaExhausted as e:
            logger.warning(
                f"[LLM] Primary provider quota exhausted. Activating fallback. Reason: {e}"
            )
            return await self._fallback.generate_structured(prompt, schema)


class FakeLLMProvider(LLMProvider):
    async def generate_structured(self, prompt: str, schema: Type[T]) -> T:
        if schema.__name__ == "GeneratedPersona":
            from app.schemas.persona import GeneratedPersona, GeneratedResearchThread, GeneratedResearchQuestion
            return GeneratedPersona(
                voice_style="Analytical and concise",
                technicality=0.8,
                skepticism=0.9,
                formality=0.7,
                preferred_content_types=["Research Papers", "Technical Docs"],
                avoided_content_types=["Hype pieces", "Marketing material"],
                editorial_principles=["Evidence over hype", "Distinguish fact from interpretation"],
                evidence_preferences=["Primary sources", "Reproducible studies"],
                research_threads=[
                    GeneratedResearchThread(
                        title="Thread 1",
                        description="Test description 1",
                        priority=0.8,
                        questions=[
                            GeneratedResearchQuestion(question="Q1", importance=0.9, confidence=0.4),
                            GeneratedResearchQuestion(question="Q2", importance=0.7, confidence=0.6)
                        ]
                    ),
                    GeneratedResearchThread(
                        title="Thread 2",
                        description="Test description 2",
                        priority=0.9,
                        questions=[
                            GeneratedResearchQuestion(question="Q3", importance=0.8, confidence=0.3),
                            GeneratedResearchQuestion(question="Q4", importance=0.9, confidence=0.2)
                        ]
                    ),
                    GeneratedResearchThread(
                        title="Thread 3",
                        description="Test description 3",
                        priority=0.7,
                        questions=[
                            GeneratedResearchQuestion(question="Q5", importance=0.6, confidence=0.5),
                            GeneratedResearchQuestion(question="Q6", importance=0.7, confidence=0.7)
                        ]
                    )
                ]
            )
            
        if schema.__name__ == "GeneratedResearchQueries":
            from app.schemas.research import GeneratedResearchQueries, GeneratedResearchQuery
            return GeneratedResearchQueries(
                queries=[
                    GeneratedResearchQuery(query="Test Query 1", angle="OVERVIEW", reason="Get broad context."),
                    GeneratedResearchQuery(query="Test Query 2", angle="EMPIRICAL", reason="Find hard data.")
                ]
            )
            
        if schema.__name__ == "GeneratedEvidenceExtraction":
            from app.schemas.research import GeneratedEvidenceExtraction, ExtractedEvidence
            
            # Simple check if there's fake test content meant to trigger grounded extraction
            if "Grounded Claim Test Content" in prompt:
                evidence_text = "Grounded Claim Test Content"
            else:
                evidence_text = "This text is magically in the source"
                
            return GeneratedEvidenceExtraction(
                evidence=[
                    ExtractedEvidence(
                        claim="Fake extracted claim",
                        evidence_text=evidence_text,
                        context="Test context",
                        relevance_score=0.9,
                        confidence=0.8,
                        polarity="SUPPORTS"
                    )
                ]
            )
            
        if schema.__name__ == "GeneratedBeliefSynthesis":
            from app.schemas.belief import GeneratedBeliefSynthesis, GeneratedBelief
            import re
            
            # Find any evidence IDs in the prompt
            ids = re.findall(r"ID: ([-_a-zA-Z0-9]+)", prompt)
            supports = [ids[0]] if len(ids) > 0 else []
            contradicts = [ids[1]] if len(ids) > 1 else []
            
            return GeneratedBeliefSynthesis(
                beliefs=[
                    GeneratedBelief(
                        statement="Fake synthesized belief.",
                        scope="General testing",
                        importance=0.9,
                        initial_confidence=0.6,
                        supporting_evidence_ids=supports,
                        contradicting_evidence_ids=contradicts,
                        qualifying_evidence_ids=[]
                    )
                ]
            )
            
        if schema.__name__ == "BeliefRevisionAnalysis":
            from app.schemas.belief import BeliefRevisionAnalysis, EvidenceAnalysis
            import re
            
            ids = re.findall(r"ID: ([-_a-zA-Z0-9]+)", prompt)
            rel = "SUPPORTS"
            if "contradict" in prompt.lower():
                rel = "CONTRADICTS"
                
            analyses = []
            for ev_id in ids:
                analyses.append(
                    EvidenceAnalysis(
                        evidence_id=ev_id,
                        relationship=rel,
                        reason="Determined by fake LLM."
                    )
                )
            
            return BeliefRevisionAnalysis(belief_id="ignored", analyses=analyses)

        elif schema.__name__ == "GeneratedEditorialCandidate":
            from app.schemas.editorial import GeneratedEditorialCandidate
            
            sig = 0.5
            rel = 0.8
            if "contradict" in prompt.lower():
                sig = 0.9  # High significance for contradictions
                
            return GeneratedEditorialCandidate(
                headline="Fake Editorial Headline",
                summary="Fake editorial summary.",
                editorial_significance=sig,
                relevance_score=rel
            )
            
        elif schema.__name__ == "GeneratedPost":
            from app.schemas.editorial import GeneratedPost, GeneratedEditorialRationale
            import random
            import string
            
            # Generate enough unique keywords to bypass the 65% overlap check
            # We must use only lowercase alphabet letters because the quality gate uses r'\b[a-z]{5,}\b'
            unique_words_list = []
            for _ in range(25):
                word = "".join(random.choices(string.ascii_lowercase, k=8))
                unique_words_list.append(word)
            unique_words = " ".join(unique_words_list)
            
            return GeneratedPost(
                text=f"This is a fake generated post about artificial intelligence safety research. {unique_words}",
                editorial_angle="Fake Angle",
                fact_claims=["Fake fact 1"],
                interpretation="Fake interpretation",
                uncertainty_level="Low",
                rationale=GeneratedEditorialRationale(
                    why_selected="Fake why selected",
                    why_now="Fake why now",
                    why_not_alternatives="Fake alternatives",
                    memory_used="Fake memory used",
                    belief_change="Fake belief change",
                    evidence_basis="Fake evidence basis"
                ),
                source_ids=[]
            )
            
        else:
            raise ValueError(f"Unknown schema type: {schema.__name__}")


# ---------------------------------------------------------------------------
# Provider factory functions
# ---------------------------------------------------------------------------

def get_llm_provider() -> LLMProvider:
    """
    Returns the primary LLM provider (strong model).
    Wraps with WithFallbackLLMProvider if HF fallback is configured.
    """
    if settings.llm_provider == "fake":
        return FakeLLMProvider()

    primary = DefaultLLMProvider(model=settings.llm_model)

    if settings.llm_fallback_provider == "huggingface" and settings.llm_fallback_api_key:
        fallback = HuggingFaceLLMProvider(model=settings.llm_fallback_model)
        logger.info(
            f"[LLM] WithFallbackLLMProvider active: primary=groq/{settings.llm_model}, "
            f"fallback=huggingface/{settings.llm_fallback_model}"
        )
        return WithFallbackLLMProvider(primary=primary, fallback=fallback)

    return primary


def get_fast_llm_provider() -> LLMProvider:
    """
    Returns a provider using the fast model for high-volume operations
    (query generation, evidence extraction).
    Falls back to the strong model if no fast model is configured.
    Wraps with HF fallback if configured.
    """
    if settings.llm_provider == "fake":
        return FakeLLMProvider()

    model = settings.effective_fast_model
    primary = DefaultLLMProvider(model=model)

    if settings.llm_fallback_provider == "huggingface" and settings.llm_fallback_api_key:
        fallback = HuggingFaceLLMProvider(model=settings.llm_fallback_model)
        return WithFallbackLLMProvider(primary=primary, fallback=fallback)

    return primary

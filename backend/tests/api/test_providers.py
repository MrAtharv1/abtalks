"""
Real provider integration tests (require RUN_REAL_PROVIDER_TESTS=1) and
unit tests for rate-limit classification, retry logic, and fallback behavior
that run in the standard test suite (no external API required).
"""
import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.provider import (
    DefaultLLMProvider,
    HuggingFaceLLMProvider,
    WithFallbackLLMProvider,
    FakeLLMProvider,
    ProviderQuotaExhausted,
    _classify_429,
    _parse_retry_after_seconds,
)
from app.schemas.persona import GeneratedPersona


# ---------------------------------------------------------------------------
# Unit tests for 429 classification helpers (no network required)
# ---------------------------------------------------------------------------

class TestClassify429:
    def test_tpd_message_detected(self):
        msg = json.dumps({"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 100000"}})
        assert _classify_429(msg) == "tpd"

    def test_tpm_message_detected(self):
        msg = json.dumps({"error": {"message": "Rate limit reached on tokens per minute (TPM): Limit 6000"}})
        assert _classify_429(msg) == "tpm"

    def test_unknown_defaults_to_tpm(self):
        assert _classify_429("some random error") == "tpm"

    def test_tpd_keyword_in_message(self):
        msg = json.dumps({"error": {"message": "daily quota exceeded TPD limit"}})
        assert _classify_429(msg) == "tpd"


class TestParseRetryAfter:
    def test_seconds_only(self):
        msg = "Please try again in 5.215s."
        assert abs(_parse_retry_after_seconds(msg) - 5.215) < 0.001

    def test_minutes_and_seconds(self):
        msg = "Please try again in 13m49.44s."
        expected = 13 * 60 + 49.44
        assert abs(_parse_retry_after_seconds(msg) - expected) < 0.001

    def test_no_retry_info(self):
        assert _parse_retry_after_seconds("some other error") == 0.0


# ---------------------------------------------------------------------------
# Unit tests for DefaultLLMProvider 429 behavior (mocked HTTP)
# ---------------------------------------------------------------------------

TPM_429_BODY = json.dumps({
    "error": {
        "message": "Rate limit reached for model `llama-3.3-70b-versatile` on tokens per minute (TPM): "
                   "Limit 12000, Used 11000. Please try again in 5.0s.",
        "type": "tokens",
        "code": "rate_limit_exceeded"
    }
})

TPD_429_BODY = json.dumps({
    "error": {
        "message": "Rate limit reached for model `llama-3.3-70b-versatile` on tokens per day (TPD): "
                   "Limit 100000, Used 99708. Please try again in 13m49.44s.",
        "type": "tokens",
        "code": "rate_limit_exceeded"
    }
})

VALID_PERSONA_BODY = json.dumps({
    "voice_style": "Analytical",
    "technicality": 0.8,
    "skepticism": 0.7,
    "formality": 0.9,
    "preferred_content_types": ["Research papers"],
    "avoided_content_types": ["Opinion pieces"],
    "editorial_principles": ["Evidence-based"],
    "evidence_preferences": ["Peer-reviewed"],
    "research_threads": [
        {
            "title": "AI Ethics",
            "description": "Ethics of AI",
            "priority": 0.9,
            "questions": [
                {"question": "Q1", "importance": 0.8, "confidence": 0.4},
                {"question": "Q2", "importance": 0.7, "confidence": 0.5}
            ]
        },
        {
            "title": "AI Safety",
            "description": "Safety research",
            "priority": 0.8,
            "questions": [
                {"question": "Q3", "importance": 0.9, "confidence": 0.3},
                {"question": "Q4", "importance": 0.6, "confidence": 0.6}
            ]
        },
        {
            "title": "AI Governance",
            "description": "Policy and governance",
            "priority": 0.7,
            "questions": [
                {"question": "Q5", "importance": 0.7, "confidence": 0.5},
                {"question": "Q6", "importance": 0.8, "confidence": 0.4}
            ]
        }
    ]
})


def _make_response(status_code: int, body: str):
    """Create a minimal mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.json.return_value = json.loads(body)
    return resp


def _make_choices_response(content: str):
    body = json.dumps({
        "choices": [{"message": {"content": content}}]
    })
    return _make_response(200, body)


@pytest.mark.asyncio
async def test_tpd_429_raises_quota_exhausted():
    """TPD 429 must raise ProviderQuotaExhausted immediately — no retry."""
    provider = DefaultLLMProvider(model="llama-3.3-70b-versatile")
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_response(429, TPD_429_BODY)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        with pytest.raises(ProviderQuotaExhausted):
            await provider.generate_structured("test prompt", GeneratedPersona)

    # Must only call once — no retry on TPD.
    assert call_count == 1


@pytest.mark.asyncio
async def test_tpm_429_raises_quota_exhausted_immediately():
    """TPM 429 must raise ProviderQuotaExhausted immediately — no retry."""
    provider = DefaultLLMProvider(model="llama-3.3-70b-versatile")
    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return _make_response(429, TPM_429_BODY)

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        with pytest.raises(ProviderQuotaExhausted, match="TPM rate limit exceeded"):
            await provider.generate_structured("test prompt", GeneratedPersona)

    # 1 initial call, no retries
    assert call_count == 1


@pytest.mark.asyncio
async def test_valid_structured_response_accepted():
    """A well-formed JSON response must parse and validate correctly."""
    provider = DefaultLLMProvider(model="llama-3.3-70b-versatile")

    async def mock_post(*args, **kwargs):
        return _make_choices_response(VALID_PERSONA_BODY)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        result = await provider.generate_structured("test prompt", GeneratedPersona)

    assert result.voice_style == "Analytical"
    assert result.technicality == 0.8
    assert len(result.research_threads) == 3


@pytest.mark.asyncio
async def test_malformed_json_raises_explicitly():
    """Malformed JSON from the model must raise — never silently accepted."""
    provider = DefaultLLMProvider(model="llama-3.3-70b-versatile")

    malformed = '{"voice_style": "Analytical", "technicality": 0. nine}'

    async def mock_post(*args, **kwargs):
        return _make_choices_response(malformed)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception, match="Failed to parse or validate JSON"):
            await provider.generate_structured("test prompt", GeneratedPersona)


@pytest.mark.asyncio
async def test_invalid_numeric_syntax_raises_explicitly():
    """Invalid numeric syntax in JSON must raise, never be silently coerced."""
    provider = DefaultLLMProvider(model="llama-3.3-70b-versatile")

    # Valid JSON keys but wrong types (confidence as string instead of float)
    invalid = json.dumps({
        "voice_style": "Analytical",
        "technicality": "high",  # should be float 0..1
        "skepticism": 0.7,
        "formality": 0.9,
        "preferred_content_types": [],
        "avoided_content_types": [],
        "editorial_principles": [],
        "evidence_preferences": [],
        "research_threads": []
    })

    async def mock_post(*args, **kwargs):
        return _make_choices_response(invalid)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        with pytest.raises(Exception):
            await provider.generate_structured("test prompt", GeneratedPersona)


# ---------------------------------------------------------------------------
# Unit tests for WithFallbackLLMProvider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_not_called_when_primary_succeeds():
    """When primary succeeds, fallback must NOT be invoked."""
    primary = AsyncMock()
    primary.generate_structured = AsyncMock(return_value="primary_result")
    fallback = AsyncMock()
    fallback.generate_structured = AsyncMock(return_value="fallback_result")

    provider = WithFallbackLLMProvider(primary=primary, fallback=fallback)
    result = await provider.generate_structured("prompt", GeneratedPersona)

    assert result == "primary_result"
    fallback.generate_structured.assert_not_called()


@pytest.mark.asyncio
async def test_fallback_called_when_primary_quota_exhausted():
    """ProviderQuotaExhausted from primary must activate the fallback."""
    primary = AsyncMock()
    primary.generate_structured = AsyncMock(
        side_effect=ProviderQuotaExhausted("Groq TPD exhausted")
    )
    fallback = AsyncMock()
    fallback.generate_structured = AsyncMock(return_value="fallback_result")

    provider = WithFallbackLLMProvider(primary=primary, fallback=fallback)
    result = await provider.generate_structured("prompt", GeneratedPersona)

    assert result == "fallback_result"
    fallback.generate_structured.assert_called_once()


@pytest.mark.asyncio
async def test_both_fail_raises_explicitly():
    """When both primary and fallback fail, the exception must propagate."""
    primary = AsyncMock()
    primary.generate_structured = AsyncMock(
        side_effect=ProviderQuotaExhausted("Groq TPD exhausted")
    )
    fallback = AsyncMock()
    fallback.generate_structured = AsyncMock(
        side_effect=ProviderQuotaExhausted("HF also exhausted")
    )

    provider = WithFallbackLLMProvider(primary=primary, fallback=fallback)

    with pytest.raises(ProviderQuotaExhausted):
        await provider.generate_structured("prompt", GeneratedPersona)


@pytest.mark.asyncio
async def test_non_quota_error_from_primary_propagates_without_fallback():
    """Non-quota errors (e.g. network, auth) must propagate — not trigger fallback."""
    primary = AsyncMock()
    primary.generate_structured = AsyncMock(
        side_effect=Exception("Auth error 401")
    )
    fallback = AsyncMock()
    fallback.generate_structured = AsyncMock(return_value="fallback_result")

    provider = WithFallbackLLMProvider(primary=primary, fallback=fallback)

    with pytest.raises(Exception, match="Auth error 401"):
        await provider.generate_structured("prompt", GeneratedPersona)

    fallback.generate_structured.assert_not_called()


# ---------------------------------------------------------------------------
# Verify FakeLLMProvider unchanged (existing behavior)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fake_provider_persona_unchanged():
    """FakeLLMProvider must continue to work as before."""
    provider = FakeLLMProvider()
    result = await provider.generate_structured("any prompt", GeneratedPersona)
    assert result is not None
    assert len(result.voice_style) > 0
    assert len(result.research_threads) >= 3


# ---------------------------------------------------------------------------
# Real provider integration tests (require RUN_REAL_PROVIDER_TESTS=1)
# ---------------------------------------------------------------------------

pytestmark_real = pytest.mark.skipif(
    os.getenv("RUN_REAL_PROVIDER_TESTS") != "1",
    reason="Skipping real provider tests. Set RUN_REAL_PROVIDER_TESTS=1 to run."
)


@pytest.mark.asyncio
@pytestmark_real
async def test_groq_strong_model_generation():
    """Real Groq strong model must return a valid GeneratedPersona."""
    from app.llm.provider import get_llm_provider
    provider = get_llm_provider()
    prompt = "Create a persona for an AI security researcher focusing on adversarial ML."
    persona = await provider.generate_structured(prompt, GeneratedPersona)
    assert persona is not None
    assert len(persona.voice_style) > 0
    assert len(persona.research_threads) >= 3


@pytest.mark.asyncio
@pytestmark_real
async def test_groq_fast_model_generation():
    """Real Groq fast model must return a valid GeneratedPersona."""
    from app.llm.provider import get_fast_llm_provider
    provider = get_fast_llm_provider()
    prompt = "Create a persona for an AI security researcher focusing on adversarial ML."
    persona = await provider.generate_structured(prompt, GeneratedPersona)
    assert persona is not None
    assert len(persona.voice_style) > 0


@pytest.mark.asyncio
@pytestmark_real
async def test_tavily_search_provider():
    """Real Tavily search must return results."""
    from app.research.search import DefaultSearchProvider
    provider = DefaultSearchProvider()
    results = await provider.search("latest AI advancements 2024", limit=2)
    assert results is not None
    assert len(results) > 0
    assert len(results[0].title) > 0
    assert len(results[0].url) > 0

import pytest
from app.llm.provider import DefaultLLMProvider, HuggingFaceLLMProvider, WithFallbackLLMProvider, ProviderQuotaExhausted
from pydantic import BaseModel
from unittest.mock import patch, MagicMock, AsyncMock

class DummySchema(BaseModel):
    value: str

@pytest.mark.asyncio
async def test_groq_capability_normalization():
    # Verify DefaultLLMProvider uses response_format={"type": "json_object"}
    provider = DefaultLLMProvider(model="test-model")
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # We don't care about the response, just the payload sent
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"value": "test"}'}}], "usage": {"total_tokens": 10}}
        mock_post.return_value = mock_response
        
        await provider.generate_structured("test prompt", DummySchema)
        
        # Check that response_format is in the payload
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        assert "response_format" in payload
        assert payload["response_format"] == {"type": "json_object"}

@pytest.mark.asyncio
async def test_hf_capability_normalization():
    # Verify HuggingFaceLLMProvider omits response_format
    provider = HuggingFaceLLMProvider(model="test-model")
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # We don't care about the response, just the payload sent
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": '{"value": "test"}'}}]}
        mock_post.return_value = mock_response
        
        with patch("app.config.settings.llm_fallback_api_key", "dummy"):
            await provider.generate_structured("test prompt", DummySchema)
        
        # Check that response_format is NOT in the payload
        _, kwargs = mock_post.call_args
        payload = kwargs.get("json", {})
        assert "response_format" not in payload

@pytest.mark.asyncio
async def test_fallback_delegation():
    # Verify WithFallbackLLMProvider cleanly delegates on ProviderQuotaExhausted
    primary = MagicMock()
    primary.generate_structured = AsyncMock(side_effect=ProviderQuotaExhausted("limit"))
    
    fallback = MagicMock()
    fallback.generate_structured = AsyncMock(return_value=DummySchema(value="fallback"))
    
    provider = WithFallbackLLMProvider(primary, fallback)
    
    result = await provider.generate_structured("test prompt", DummySchema)
    
    assert result.value == "fallback"
    fallback.generate_structured.assert_called_once_with("test prompt", DummySchema)

"""Unit tests for GeminiProvider mocking HTTP interactions, error cases, and grounding metadata."""
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.evaluator.providers.gemini_provider import GeminiModelProvider


@pytest.mark.asyncio
async def test_gemini_provider_init_and_config():
    """Verify GeminiModelProvider initializes correctly with API key and custom model."""
    provider = GeminiModelProvider(api_key="AIzaSyTestSecretKey123", model="gemini-1.5-flash")
    assert provider.api_key == "AIzaSyTestSecretKey123"
    assert provider.default_model == "gemini-1.5-flash"
    assert provider.provider_name == "gemini"


@pytest.mark.asyncio
async def test_gemini_provider_missing_api_key():
    """Verify GeminiModelProvider fails with clear error if api_key is empty."""
    provider = GeminiModelProvider(api_key="", model="gemini-1.5-flash")
    resp = await provider.query("Test query")
    assert resp.is_success is False
    assert "LLM_API_KEY is not configured" in resp.error_message
    assert resp.is_retryable is False


@pytest.mark.asyncio
async def test_gemini_provider_successful_query_with_grounding_and_tokens():
    """Verify successful Gemini API response parsing including tokens and search grounding citations."""
    provider = GeminiModelProvider(api_key="AIzaSyTestSecretKey123", model_name="gemini-1.5-pro")

    mock_gemini_payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": "Linear is a modern project tracking tool designed specifically for software teams."
                        }
                    ],
                    "role": "model"
                },
                "finishReason": "STOP",
                "groundingMetadata": {
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://linear.app/features",
                                "title": "Linear Features"
                            }
                        },
                        {
                            "web": {
                                "uri": "https://techcrunch.com/linear-review",
                                "title": "TechCrunch Review"
                            }
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 24,
            "candidatesTokenCount": 48,
            "totalTokenCount": 72
        }
    }

    mock_response = httpx.Response(
        status_code=200,
        json=mock_gemini_payload,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        resp = await provider.query("What is Linear?")

        assert resp.is_success is True
        assert "Linear is a modern project tracking tool" in resp.text
        assert resp.provider == "gemini"
        assert resp.model_name == "gemini-1.5-pro"
        assert resp.tokens_used == 72
        assert resp.prompt_tokens == 24
        assert resp.completion_tokens == 48
        assert len(resp.grounding_citations) == 2
        assert resp.grounding_citations[0] == "https://linear.app/features"
        assert resp.grounding_citations[1] == "https://techcrunch.com/linear-review"

        # Check call arguments: verify API key is sent in HEADER, NOT IN URL query params
        call_kwargs = mock_post.call_args.kwargs
        call_url = mock_post.call_args.args[0] if mock_post.call_args.args else call_kwargs.get("url")
        headers = call_kwargs.get("headers", {})
        
        assert "key=" not in str(call_url)
        assert headers.get("x-goog-api-key") == "AIzaSyTestSecretKey123"


@pytest.mark.asyncio
async def test_gemini_provider_rate_limit_429():
    """Verify HTTP 429 response is classified as retryable rate limit error and redacts secrets."""
    provider = GeminiModelProvider(api_key="AIzaSyTestSecretKey123", model_name="gemini-1.5-flash")

    mock_response = httpx.Response(
        status_code=429,
        text='{"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota)."}}',
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        resp = await provider.query("Test query")

        assert resp.is_success is False
        assert resp.is_retryable is True
        assert "Rate limit exceeded" in resp.error_message
        assert "AIzaSyTestSecretKey123" not in resp.error_message


@pytest.mark.asyncio
async def test_gemini_provider_auth_failure_401():
    """Verify HTTP 401 response is classified as non-retryable authentication failure."""
    provider = GeminiModelProvider(api_key="InvalidKeyABC123", model_name="gemini-1.5-flash")

    mock_response = httpx.Response(
        status_code=401,
        text='{"error": {"code": 401, "message": "API key not valid. Please pass a valid API key."}}',
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        resp = await provider.query("Test query")

        assert resp.is_success is False
        assert resp.is_retryable is False
        assert "Authentication failed" in resp.error_message
        assert "InvalidKeyABC123" not in resp.error_message


@pytest.mark.asyncio
async def test_gemini_provider_timeout_handling():
    """Verify HTTP timeout is caught cleanly and flagged as retryable."""
    provider = GeminiModelProvider(api_key="AIzaSyTestSecretKey123", model_name="gemini-1.5-flash")

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Connection timed out")):
        resp = await provider.query("Test query")

        assert resp.is_success is False
        assert resp.is_retryable is True
        assert "timed out" in resp.error_message.lower()


@pytest.mark.asyncio
async def test_gemini_provider_safety_block_handling():
    """Verify responses blocked by safety filters are handled gracefully with detailed reasons."""
    provider = GeminiModelProvider(api_key="AIzaSyTestSecretKey123", model_name="gemini-1.5-flash")

    safety_payload = {
        "candidates": [
            {
                "finishReason": "SAFETY",
                "safetyRatings": [
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "probability": "HIGH"}
                ]
            }
        ]
    }

    mock_response = httpx.Response(
        status_code=200,
        json=safety_payload,
        request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent")
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        resp = await provider.query("Dangerous query")

        assert resp.is_success is False
        assert resp.is_retryable is False
        assert "content was blocked" in resp.error_message
        assert "SAFETY" in resp.error_message

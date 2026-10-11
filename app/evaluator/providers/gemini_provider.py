"""Google Gemini API Provider for Engine 3 AI Visibility Evaluation."""
import time
import json
import re
import logging
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings
from app.evaluator.providers.base import AIModelProvider, ProviderResponse

logger = logging.getLogger(__name__)


def _sanitize_error_message(msg: str) -> str:
    """Strip any accidental API keys from error messages."""
    if not msg:
        return ""
    # Strip Gemini AIza keys
    msg = re.sub(r"AIza[0-9A-Za-z-_]{35}", "[REDACTED_API_KEY]", msg)
    # Strip key query param
    msg = re.sub(r"key=[^&\s]+", "key=[REDACTED]", msg)
    return msg


class GeminiModelProvider(AIModelProvider):
    """
    Live AI model provider using Google Gemini API with bounded timeouts,
    rate limits, token usage tracking, and citation extraction from groundingMetadata.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.LLM_API_KEY
        self._default_model = model or model_name or settings.LLM_MODEL or "gemini-1.5-flash"

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return self._default_model

    async def query(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.2
    ) -> ProviderResponse:
        active_model = model_name or self.default_model

        if not self.api_key:
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=0,
                is_success=False,
                is_retryable=False,
                error_message="LLM_API_KEY is not configured for Google Gemini provider. Set LLM_API_KEY in environment."
            )

        start_time = time.time()
        # Security: Send API key via header, NEVER in URL query string to prevent logging leaks
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        payload: Dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                latency = int((time.time() - start_time) * 1000)

                if res.status_code != 200:
                    status = res.status_code
                    raw_err = res.text[:300]
                    if status == 429:
                        prefix = "Rate limit exceeded (HTTP 429)"
                    elif status in (401, 403):
                        prefix = f"Authentication failed (HTTP {status})"
                    else:
                        prefix = f"Gemini API returned HTTP {status}"

                    clean_err = _sanitize_error_message(f"{prefix}: {raw_err}")
                    logger.warning(clean_err)

                    # Classify retryability: 429 and 5xx are retryable; 400/401/403/404 are permanent
                    is_retryable = status in (429, 500, 502, 503, 504)

                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        is_retryable=is_retryable,
                        error_message=clean_err,
                        metadata={"status_code": status}
                    )

                data = res.json()

                # Check prompt feedback (safety blocking)
                prompt_feedback = data.get("promptFeedback", {})
                block_reason = prompt_feedback.get("blockReason")
                if block_reason:
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        is_retryable=False,
                        error_message=f"Prompt blocked by Gemini safety filters (reason: {block_reason}).",
                        metadata=data
                    )

                candidates = data.get("candidates", [])
                if not candidates:
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        is_retryable=False,
                        error_message="Gemini returned 0 candidates in response.",
                        metadata=data
                    )

                first_cand = candidates[0]
                finish_reason = first_cand.get("finishReason")

                if finish_reason in ("SAFETY", "RECITATION", "BLOCKLIST"):
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        is_retryable=False,
                        error_message=f"Gemini content was blocked by safety filters (finishReason: {finish_reason}).",
                        metadata=data
                    )

                content_parts = first_cand.get("content", {}).get("parts", [])
                response_text = "".join(p.get("text", "") for p in content_parts)

                if not response_text.strip():
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        is_retryable=False,
                        error_message=f"Gemini returned empty text content (finishReason: {finish_reason or 'UNKNOWN'}).",
                        metadata=data
                    )

                usage = data.get("usageMetadata", {})
                prompt_tokens = usage.get("promptTokenCount")
                completion_tokens = usage.get("candidatesTokenCount")
                total_tokens = usage.get("totalTokenCount") or ((prompt_tokens or 0) + (completion_tokens or 0))

                # Extract web grounding citations if available
                citations: List[str] = []
                grounding = first_cand.get("groundingMetadata", {})
                for chunk in grounding.get("groundingChunks", []):
                    web = chunk.get("web", {})
                    uri = web.get("uri")
                    if uri and uri.startswith("http"):
                        citations.append(uri)

                return ProviderResponse(
                    text=response_text,
                    provider=self.provider_name,
                    model_name=active_model,
                    latency_ms=latency,
                    tokens_used=total_tokens if total_tokens > 0 else None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    grounding_citations=citations,
                    is_success=True,
                    is_retryable=False,
                    metadata={
                        "finish_reason": finish_reason,
                        "grounding_citations": citations,
                        "usage": usage
                    }
                )

        except httpx.TimeoutException:
            latency = int((time.time() - start_time) * 1000)
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=latency,
                is_success=False,
                is_retryable=True,
                error_message="Request to Gemini API timed out after 25 seconds."
            )
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            clean_err = _sanitize_error_message(str(e))
            logger.exception(f"Unexpected error communicating with Gemini API: {clean_err}")
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=latency,
                is_success=False,
                is_retryable=False,
                error_message=f"Gemini API client error: {clean_err}"
            )


# Alias for backward-compatibility
GeminiProvider = GeminiModelProvider


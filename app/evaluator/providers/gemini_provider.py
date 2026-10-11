"""Google Gemini API Provider for Engine 3 AI Visibility Evaluation."""
import time
import json
import logging
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings
from app.evaluator.providers.base import AIModelProvider, ProviderResponse

logger = logging.getLogger(__name__)


class GeminiModelProvider(AIModelProvider):
    """
    Live AI model provider using Google Gemini API with bounded timeouts,
    rate limits, token usage tracking, and citation extraction from groundingMetadata.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.LLM_API_KEY
        self._default_model = model or settings.LLM_MODEL or "gemini-1.5-flash"

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
                error_message="LLM_API_KEY is not configured for Google Gemini provider. Set LLM_API_KEY in environment."
            )

        start_time = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{active_model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}

        parts = []
        if system_instruction:
            parts.append({"text": f"SYSTEM INSTRUCTION: {system_instruction}"})
        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                latency = int((time.time() - start_time) * 1000)

                if res.status_code != 200:
                    err_msg = f"Gemini API returned HTTP {res.status_code}: {res.text[:200]}"
                    logger.warning(err_msg)
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        error_message=err_msg,
                        metadata={"status_code": res.status_code}
                    )

                data = res.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return ProviderResponse(
                        text="",
                        provider=self.provider_name,
                        model_name=active_model,
                        latency_ms=latency,
                        is_success=False,
                        error_message="Gemini returned 0 candidates in response.",
                        metadata=data
                    )

                first_cand = candidates[0]
                content_parts = first_cand.get("content", {}).get("parts", [])
                response_text = "".join(p.get("text", "") for p in content_parts)

                usage = data.get("usageMetadata", {})
                tokens = usage.get("totalTokenCount")

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
                    tokens_used=tokens,
                    is_success=True,
                    metadata={
                        "finish_reason": first_cand.get("finishReason"),
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
                error_message="Request to Gemini API timed out after 25 seconds."
            )
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            logger.exception(f"Unexpected error communicating with Gemini API: {e}")
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=latency,
                is_success=False,
                error_message=f"Gemini API client error: {str(e)}"
            )

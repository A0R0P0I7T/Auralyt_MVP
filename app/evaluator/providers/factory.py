"""Factory for selecting active AI Model Provider in Engine 3."""
from typing import Optional
from app.core.config import settings
from app.evaluator.providers.base import AIModelProvider
from app.evaluator.providers.mock_provider import MockAIModelProvider
from app.evaluator.providers.gemini_provider import GeminiModelProvider


def get_evaluator_provider(provider_name: Optional[str] = None) -> AIModelProvider:
    """
    Select active provider adapter.
    If provider_name is explicitly 'gemini' or settings specify gemini with an API key,
    returns GeminiModelProvider. Otherwise returns MockAIModelProvider.
    """
    selected = (provider_name or settings.LLM_PROVIDER or "mock").lower()

    if selected == "gemini":
        if settings.LLM_API_KEY:
            return GeminiModelProvider()
        # If gemini requested but no API key configured, return Mock with notice
        return MockAIModelProvider()

    return MockAIModelProvider()

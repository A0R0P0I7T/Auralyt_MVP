"""Base classes and interfaces for Engine 3 AI Model Providers."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ProviderResponse(BaseModel):
    """Normalized response from an AI Model Provider."""
    text: str = Field(default="", description="Verbatim raw response text from the model")
    provider: str = Field(description="Provider identifier (e.g. mock, gemini, openai)")
    model_name: str = Field(description="Exact model identifier (e.g. mock-evaluator, gemini-1.5-flash)")
    latency_ms: int = Field(default=0, description="End-to-end request latency in milliseconds")
    tokens_used: Optional[int] = Field(default=None, description="Reported token count if available")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw metadata from provider (headers, citations, usage)")
    is_success: bool = Field(default=True, description="Whether the request succeeded")
    error_message: Optional[str] = Field(default=None, description="Error message if request failed")


class AIModelProvider(ABC):
    """Abstract base class for all AI Model evaluation providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name string."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier."""
        pass

    @abstractmethod
    async def query(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.2
    ) -> ProviderResponse:
        """Execute query against AI model and return normalized response."""
        pass

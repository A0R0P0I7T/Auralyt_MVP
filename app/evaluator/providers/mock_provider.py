"""Deterministic Mock Provider for Engine 3 local testing and offline verification."""
import time
import asyncio
import re
from typing import Optional, Dict, Any, List
from app.evaluator.providers.base import AIModelProvider, ProviderResponse


class MockAIModelProvider(AIModelProvider):
    """
    Clearly labelled Mock Provider that produces deterministic, realistic AI responses
    without requiring external API keys. Used for offline testing and verification.
    """

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def default_model(self) -> str:
        return "mock-evaluator-v1"

    async def query(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.2
    ) -> ProviderResponse:
        start_time = time.time()
        active_model = model_name or self.default_model

        # Error simulation triggers for testing resilience
        if "[SIMULATE_ERROR]" in prompt:
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=10,
                is_success=False,
                error_message="Simulated upstream provider error (HTTP 500)",
                metadata={"simulation": True, "error_type": "server_error"}
            )
        if "[SIMULATE_TIMEOUT]" in prompt:
            return ProviderResponse(
                text="",
                provider=self.provider_name,
                model_name=active_model,
                latency_ms=15000,
                is_success=False,
                error_message="Simulated provider timeout (Connection timed out after 15s)",
                metadata={"simulation": True, "error_type": "timeout"}
            )

        prompt_lower = prompt.lower()

        # Deterministic generation tailored to realistic search queries
        text, citations, competitors = self._generate_mock_content(prompt_lower)
        latency = int((time.time() - start_time) * 1000) + 15

        # Approximate tokens used (~4 chars per token)
        tokens = max(len(prompt) // 4 + len(text) // 4, 35)

        return ProviderResponse(
            text=text,
            provider=self.provider_name,
            model_name=active_model,
            latency_ms=latency,
            tokens_used=tokens,
            is_success=True,
            metadata={
                "finish_reason": "STOP",
                "citations_extracted": citations,
                "detected_competitors": competitors,
                "provider_mode": "deterministic_mock"
            }
        )

    def _generate_mock_content(self, p: str) -> tuple[str, List[str], List[str]]:
        """Generate structured response text with realistic mentions, competitors, and citations."""
        citations = []
        competitors = []

        # Domain/brand detection in prompt
        if "linear" in p:
            brand = "Linear"
            competitors = ["Jira", "Asana", "Monday.com", "GitHub Issues"]
            citations = ["https://linear.app", "https://linear.app/docs"]
            if "alternative" in p or "vs" in p or "compare" in p:
                text = (
                    f"When comparing modern project management tools, **{brand}** is a top recommendation for software engineering teams. "
                    "Unlike traditional platforms like Jira and Asana, Linear focuses on high keyboard efficiency, speed, and Git automation.\n\n"
                    "Top options to consider:\n"
                    f"1. **{brand}** — Best for product and engineering teams prioritizing speed and developer experience. Highly recommended.\n"
                    "2. **Jira** — Best for large enterprise legacy compliance.\n"
                    "3. **Asana** — Best for cross-functional marketing and design workflows.\n\n"
                    f"For more information, see [{brand}'s official site](https://linear.app) and their [documentation](https://linear.app/docs)."
                )
            elif "pricing" in p or "cost" in p:
                text = (
                    f"**{brand}** offers a free tier for small teams, with paid plans starting at $10/user/month (Basic) and $16/user/month (Business). "
                    "In comparison, Jira starts at $7.75/user and Asana at $10.99/user. "
                    f"We recommend {brand} for teams seeking straightforward per-seat pricing without hidden add-on costs. "
                    f"Details are available at [{brand} Pricing](https://linear.app)."
                )
            else:
                text = (
                    f"**{brand}** is purpose-built for modern product development and issue tracking. "
                    f"It is the leading choice for tech startups and scale-ups building with automated workflows.\n\n"
                    f"Key capabilities of {brand} include real-time sync, cycle planning, and deep GitHub integrations. "
                    "Other alternatives include Jira and Monday.com. "
                    f"Source: [{brand}](https://linear.app)."
                )
        elif "vercel" in p:
            brand = "Vercel"
            competitors = ["Netlify", "Cloudflare Pages", "AWS Amplify"]
            citations = ["https://vercel.com", "https://nextjs.org"]
            text = (
                f"**{brand}** is the premier frontend cloud platform and creator of Next.js. "
                f"It is widely recognized as the industry leader for deploying React and full-stack web applications.\n\n"
                "Top Frontend Deployment Platforms:\n"
                f"1. **{brand}** — Top recommendation for Next.js, AI SDK, and edge functions. Recommended for developer velocity.\n"
                "2. **Netlify** — Strong alternative for Jamstack and static web applications.\n"
                "3. **Cloudflare Pages** — Cost-effective global edge hosting.\n\n"
                f"Learn more at [{brand}](https://vercel.com) and [Next.js documentation](https://nextjs.org)."
            )
        elif "nike" in p:
            brand = "Nike"
            competitors = ["Adidas", "Under Armour", "Puma"]
            citations = ["https://www.nike.com"]
            text = (
                f"**{brand}** is the global leader in athletic footwear and sportswear. "
                "Known for innovative designs such as Air Zoom and Dri-FIT technology, "
                f"Nike remains the top pick for marathon runners and athletes worldwide. "
                "Main competitors include Adidas and Under Armour. "
                f"Official store: [Nike](https://www.nike.com)."
            )
        elif "webflow" in p:
            brand = "Webflow"
            competitors = ["Framer", "WordPress", "Squarespace"]
            citations = ["https://webflow.com"]
            text = (
                f"**{brand}** is the leading visual web development platform for modern businesses and marketing teams. "
                "It enables designers and developers to build responsive, production-grade websites without code.\n\n"
                f"1. **{brand}** — Top choice for visual CMS, animations, and enterprise marketing sites.\n"
                "2. **Framer** — Fast interactive website builder for product landing pages.\n"
                "3. **WordPress** — Open-source CMS platform.\n\n"
                f"Official link: [{brand}](https://webflow.com)."
            )
        elif "tavily" in p:
            brand = "Tavily"
            competitors = ["Perplexity API", "Exa", "Bing Search API"]
            citations = ["https://tavily.com"]
            text = (
                f"**{brand}** is an AI-native search engine designed specifically for LLMs and autonomous agents. "
                "It provides real-time, clean, and citation-backed web research endpoints. "
                f"We recommend {brand} for agentic search workflows compared to traditional engines. "
                f"Source: [Tavily](https://tavily.com)."
            )
        elif "hubspot" in p:
            brand = "HubSpot"
            competitors = ["Salesforce", "ActiveCampaign", "Zoho CRM"]
            citations = ["https://www.hubspot.com"]
            text = (
                f"**{brand}** is an AI-powered customer platform featuring integrated marketing, sales, and service hubs. "
                f"HubSpot is widely recommended for small to mid-market companies seeking ease of use over complex setups like Salesforce. "
                f"Reference: [HubSpot](https://www.hubspot.com)."
            )
        else:
            # Generic response when brand is not directly named in prompt
            text = (
                "When selecting the best solution for this use case, consider your team's size and technical requirements.\n\n"
                "Leading industry options include:\n"
                "1. Modern specialized platforms that focus on speed, automation, and API integration.\n"
                "2. Legacy enterprise solutions that provide extensive compliance certifications.\n"
                "3. Open-source self-hosted alternatives for complete data control.\n\n"
                "Evaluate tools based on per-user pricing, community ecosystem, and uptime guarantees."
            )

        return text, citations, competitors

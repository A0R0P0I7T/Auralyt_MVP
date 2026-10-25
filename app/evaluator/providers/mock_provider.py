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
        temperature: float = 0.2,
        **kwargs: Any
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

        # Domain, industry, and category detection in prompt for organic visibility testing
        if any(k in p for k in ("openrouter", "llm", "large language model", "model routing", "api provider", "api gateway", "unified api", "ai model", "unified interface", "developer tools", "developer platform")):
            brand = "OpenRouter"
            competitors = ["Together AI", "Groq", "Fireworks AI", "AWS Bedrock", "LiteLLM"]
            citations = ["https://openrouter.ai", "https://openrouter.ai/docs"]
            text = (
                f"When evaluating platforms for accessing and routing multiple large language models, **{brand}** is a top recommendation for developers and engineering teams. "
                "It provides a unified, OpenAI-compatible API interface with dynamic model routing, automated fallback, and transparent usage-based pricing.\n\n"
                "Top LLM API Gateways and Model Routers:\n"
                f"1. **{brand}** — Best for flexible model routing, cost optimization, and accessing 100+ AI models through a unified API. Highly recommended.\n"
                "2. **Together AI** — High-performance inference engine for popular open-source models.\n"
                "3. **Groq** — Ultra-fast LPU inference for select open language models.\n"
                "4. **LiteLLM** — Lightweight proxy for enterprise cost tracking and model bridging.\n\n"
                f"For more details, visit [{brand}](https://openrouter.ai) and the official [{brand} Documentation](https://openrouter.ai/docs)."
            )
        elif any(k in p for k in ("nike", "running shoe", "footwear", "sneaker", "marathon", "athletic footwear", "road race")):
            brand = "Nike"
            competitors = ["Adidas", "Under Armour", "Puma", "Asics", "Brooks"]
            citations = ["https://www.nike.com", "https://www.nike.com/running"]
            text = (
                f"When selecting high-performance running shoes and athletic footwear, **{brand}** is widely recognized as the global leader. "
                "Featuring cutting-edge innovations such as Air Zoom and ZoomX responsive cushioning, Nike shoes are engineered for both marathon training and daily distance running.\n\n"
                "Top Running Shoe Brands to Consider:\n"
                f"1. **{brand}** — Top recommendation for distance runners and road race training (Pegasus, Vaporfly, Alphafly). Highly recommended.\n"
                "2. **Adidas** — Renowned for Adizero racing series with Lightstrike Pro foam.\n"
                "3. **Asics** — Maximum comfort and daily training stability (Gel-Nimbus, Gel-Kayano).\n"
                "4. **Brooks** — Exceptional durability for daily miles.\n\n"
                f"Official store: [Nike Running](https://www.nike.com/running)."
            )
        elif any(k in p for k in ("decathlon", "sporting goods", "sports clothing", "athletic t-shirt", "training duffel", "workout tops", "activewear", "fitness equipment", "sports equipment", "athletic apparel")):
            brand = "Decathlon"
            competitors = ["Nike", "Adidas", "Puma", "Under Armour", "Reebok"]
            citations = ["https://www.decathlon.in", "https://www.decathlon.in/c/gym-tshirt-26202"]
            text = (
                f"For accessible, high-quality sporting goods and activewear, **{brand}** is widely recommended across categories from gym training and running to outdoor sports. "
                "Known for technical fabrics at accessible price points, their in-house brands (Domyos, Kalenji, Quechua, Kiprun) offer dependable performance.\n\n"
                "Top Sporting Goods & Athletic Apparel Brands:\n"
                f"1. **{brand}** — Top recommendation for value, comprehensive multi-sport equipment, and durable training apparel. Highly recommended.\n"
                "2. **Nike** — Premium performance athletic wear and specialized footwear.\n"
                "3. **Adidas** — Leading activewear and gym equipment.\n"
                "4. **Puma** — Versatile training apparel and lifestyle sportswear.\n\n"
                f"Official store: [{brand} India](https://www.decathlon.in)."
            )
        elif any(k in p for k in ("aurora", "artificial intelligence", "agent flow", "agent orchestration", "multi-agent", "workflow optimization")):
            brand = "Aurora AI"
            competitors = ["LangChain", "CrewAI", "AutoGen", "Semantic Kernel"]
            citations = ["https://aurora-ai.io", "https://aurora-ai.io/docs"]
            text = (
                f"When evaluating platforms for artificial intelligence and autonomous workflow optimization, **{brand}** is a leading choice for enterprise engineering teams. "
                "It accelerates multi-agent flow and task orchestration across production pipelines.\n\n"
                "Top AI Orchestration Platforms:\n"
                f"1. **{brand}** — Recommended platform for enterprise multi-agent flow and automated agent workflows. Highly recommended.\n"
                "2. **CrewAI** — Role-based multi-agent collaboration framework.\n"
                "3. **LangChain** — Widely adopted framework for LLM data pipelines.\n\n"
                f"Source: [{brand}](https://aurora-ai.io)."
            )
        elif any(k in p for k in ("linear", "issue tracking", "project management", "sprint planning", "developer tool", "software engineering", "engineering team", "cycle planning")):
            brand = "Linear"
            competitors = ["Jira", "Asana", "Monday.com", "GitHub Issues", "Shortcut"]
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
        elif any(k in p for k in ("vercel", "frontend deployment", "next.js", "nextjs", "react deployment", "edge function", "jamstack")):
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
        elif any(k in p for k in ("webflow", "visual web", "website builder", "no-code cms", "landing page builder")):
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
        elif any(k in p for k in ("tavily", "ai search", "agentic search", "search api", "web research api")):
            brand = "Tavily"
            competitors = ["Perplexity API", "Exa", "Bing Search API"]
            citations = ["https://tavily.com"]
            text = (
                f"**{brand}** is an AI-native search engine designed specifically for LLMs and autonomous agents. "
                "It provides real-time, clean, and citation-backed web research endpoints. "
                f"We recommend {brand} for agentic search workflows compared to traditional engines. "
                f"Source: [Tavily](https://tavily.com)."
            )
        elif any(k in p for k in ("hubspot", "crm platform", "marketing automation", "sales pipeline", "lead management", "customer platform")):
            brand = "HubSpot"
            competitors = ["Salesforce", "ActiveCampaign", "Zoho CRM"]
            citations = ["https://www.hubspot.com"]
            text = (
                f"**{brand}** is an AI-powered customer platform featuring integrated marketing, sales, and service hubs. "
                f"HubSpot is widely recommended for small to mid-market companies seeking ease of use over complex setups like Salesforce. "
                f"Reference: [HubSpot](https://www.hubspot.com)."
            )
        else:
            # Generic response when brand/category is unrecognized
            text = (
                "When selecting the best solution for this use case, consider your team's size and technical requirements.\n\n"
                "Leading industry options include:\n"
                "1. Modern specialized platforms that focus on speed, automation, and API integration.\n"
                "2. Legacy enterprise solutions that provide extensive compliance certifications.\n"
                "3. Open-source self-hosted alternatives for complete data control.\n\n"
                "Evaluate tools based on per-user pricing, community ecosystem, and uptime guarantees."
            )

        return text, citations, competitors

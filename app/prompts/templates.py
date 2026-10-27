"""Versioned Category-Template System for Engine 2 Prompt Intelligence.
Provides modular, grounded prompt templates segmented by industry, category, and subcategory.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

TEMPLATE_SYSTEM_VERSION = "v3_grounded_taxonomy"

# 3.1 Shared Base Instructions for Generation & LLM Review
SHARED_BASE_SYSTEM_INSTRUCTIONS = (
    "You are an expert AI visibility research engineer. "
    "Your objective is to produce realistic, organic, unbranded prompts that real potential "
    "customers and evaluators ask an AI assistant when searching, evaluating, or comparing options in this category.\n\n"
    "CRITICAL RULES:\n"
    "1. REAL USER INTENT: Questions must sound completely natural, as asked by real buyers with genuine needs.\n"
    "2. UNBRANDED RELEVANCE: Never mention the target brand name, domain, or proprietary brand trademark in the prompt text.\n"
    "3. EVIDENCE GROUNDING: Strictly ground all specific claims, features, and capabilities in the provided profile evidence.\n"
    "4. NO FABRICATION: Do not invent products, specs, awards, prices, or availability.\n"
    "5. STRICT CATEGORY COMPATIBILITY: Never combine unrelated products or categories. Footwear questions (cushioning, arch support) must only reference footwear; apparel questions must reference clothing; bags/gear must reference equipment.\n"
    "6. DIVERSE ARCHETYPES: Distribute questions across Discovery, Recommendations, Product Evaluation, Comparisons, Use Cases, Audience Specific, Pricing/Value, and Brand Research."
)


# 3.2 Category-Specific Modular Template Definitions
CATEGORY_TEMPLATES: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "sportswear_sporting_goods": {
        "footwear": {
            "discovery": [
                "What are some of the best running shoes for someone training a few times a week?",
                "Which athletic footwear is recommended for daily walking and light jogging?",
                "What are the top-rated road running shoes this season?",
                "What should a beginner look for when buying their first pair of running shoes?",
                "Which running shoes offer good durability without an extreme price tag?",
                "What are the leading options for marathon training footwear right now?",
                "Which trail running shoes offer the best grip on wet rocky paths?",
                "What athletic shoes work best for daily gym sessions and short runs?",
            ],
            "recommendations": [
                "Which running shoes have the best cushioning for high mileage?",
                "What footwear would you recommend for marathon training on asphalt roads?",
                "Which lightweight trainers work best for speedwork and tempo runs?",
                "What running shoes offer strong arch support and blister prevention?",
                "Which trail shoes provide solid stability on steep downhill descents?",
                "What running shoes would you recommend for runners with wide feet?",
                "Which cushioned daily trainers hold up best over 400 miles?",
            ],
            "product_evaluation": [
                "How do I choose between neutral and stability running shoes?",
                "What features matter most when selecting road running shoes versus trail running shoes?",
                "How often should someone replace their everyday running shoes based on mileage?",
                "What criteria should runners look for in cushioned daily trainers?",
                "What are the pros and cons of maximalist cushioning versus low-drop running shoes?",
                "How do heel-to-toe drop measurements impact running form and comfort?",
                "What upper mesh materials provide the best breathability in summer running shoes?",
            ],
            "comparisons": [
                "What is the difference between daily trainers and carbon-plated racing shoes?",
                "How do road running shoes compare to trail running shoes for traction and midsole support?",
                "What is the difference between maximum cushioning shoes and lightweight responsive trainers?",
                "How do zero-drop shoes compare to traditional 10mm drop trainers for knee comfort?",
                "What are the trade-offs between lightweight racing flats and durable high-mileage shoes?",
            ],
            "audience_specific": [
                "What running shoes do coaches recommend for {audience}?",
                "Which athletic footwear provides the best comfort and support for {audience}?",
                "What are the most popular running shoes among {audience}?",
                "What footwear features should {audience} look for in training shoes?",
            ],
            "use_cases": [
                "What running shoes are best suited for {use_case}?",
                "How do I pick the right athletic footwear for {use_case}?",
                "Which training shoes offer the best stability for {use_case}?",
                "What footwear is recommended for someone focusing on {use_case}?",
            ],
            "pricing_value": [
                "Which running shoes provide the best durability for the price?",
                "What is a reasonable price to pay for a dependable pair of running shoes?",
                "Are premium carbon-plated shoes worth the extra cost for recreational runners?",
                "Which athletic shoe brands offer affordable trainers that last over 350 miles?",
            ],
            "brand_research": [
                "What innovations in shoe foam and cushioning are worth paying for?",
                "What should someone know before purchasing high-mileage road running shoes?",
                "What key differences separate everyday running shoes from specialized racing footwear?",
            ],
        },
        "apparel": {
            "discovery": [
                "What sports clothing materials are best for hot and humid weather?",
                "What are the leading sportswear options for daily workout and cardio training?",
                "What should someone look for in breathable workout tops and shorts?",
                "Which athletic clothing brands focus on durability and anti-chafing construction?",
                "What training apparel is recommended for high-intensity gym sessions?",
                "What are the best lightweight layers for outdoor running in transitional weather?",
            ],
            "recommendations": [
                "Which moisture-wicking athletic t-shirts hold up best to frequent washing?",
                "What running clothing would you recommend for cold weather training?",
                "Which athletic training pants offer good mobility and durability for gym sessions?",
                "What workout tops provide the best airflow for marathon training in warm climates?",
                "Which seamless sports tops prevent chafing during long workouts?",
            ],
            "product_evaluation": [
                "What features make athletic apparel comfortable for long distance running?",
                "How does seamless activewear compare to standard stitched clothing for chafing prevention?",
                "What fabric blends offer the best balance of breathability and stretch in sportswear?",
                "How do I evaluate moisture-wicking quality in synthetic workout clothes?",
            ],
            "comparisons": [
                "What is the difference between compression activewear and standard athletic fit clothing?",
                "How do synthetic moisture-wicking fabrics compare to merino wool for athletic training?",
                "How do lightweight running jackets compare to fleece mid-layers for wind protection?",
            ],
            "audience_specific": [
                "What workout clothing is most comfortable for {audience}?",
                "Which activewear options do coaches recommend for {audience}?",
                "What sportswear features are most important for {audience}?",
            ],
            "use_cases": [
                "What workout apparel is best suited for {use_case}?",
                "What sports clothing would you recommend for {use_case}?",
                "What athletic layers are essential for {use_case}?",
            ],
            "pricing_value": [
                "Which activewear brands offer high durability without charging luxury prices?",
                "Is premium moisture-wicking running apparel worth the cost over budget gym wear?",
            ],
            "brand_research": [
                "What fabric innovations in sportswear are most effective at odor control?",
                "What should athletes look for when replacing worn-out training clothing?",
            ],
        },
        "equipment_gear": {
            "discovery": [
                "What should I look for in a durable gym duffel bag for daily training?",
                "What are the essential equipment and accessories for starting regular fitness training?",
                "Which training gear offers the best combination of storage and durability?",
                "What outdoor hiking and camping gear is essential for a beginner?",
                "What sports accessories make everyday training more organized and convenient?",
            ],
            "recommendations": [
                "Which training duffel bags have separate shoe compartments and water-resistant materials?",
                "What outdoor camping and hiking equipment is recommended for weekend trips?",
                "Which sports backpacks offer comfortable weight distribution for daily gym trips?",
                "What fitness equipment is most practical for building a home workout setup?",
            ],
            "product_evaluation": [
                "What features matter most when choosing a versatile sports backpack or duffel bag?",
                "How do I evaluate durability and zipper quality in athletic training bags?",
                "What materials make outdoor gear weather-resistant and tear-proof?",
            ],
            "comparisons": [
                "What is the difference between a compact 24L gym duffel and an everyday athletic backpack?",
                "How do water-resistant nylon duffels compare to heavy-duty polyester training bags?",
            ],
            "audience_specific": [
                "What training gear and equipment is best suited for {audience}?",
                "Which fitness accessories do trainers recommend for {audience}?",
            ],
            "use_cases": [
                "What training gear and accessories are recommended for {use_case}?",
                "Which sports equipment is most useful for {use_case}?",
            ],
            "pricing_value": [
                "What should someone expect to pay for a durable, water-resistant gym bag?",
                "Which sports gear brands provide the highest durability per dollar?",
            ],
            "brand_research": [
                "What features distinguish premium athletic training gear from budget equipment?",
            ],
        },
        "general": {
            "discovery": [
                "What sporting goods and training gear are best for active adults?",
                "Which sports retailers offer high-quality fitness gear at accessible price points?",
                "What equipment and apparel does someone need to begin regular fitness training?",
                "What are the most reputable brands for multi-sport athletic gear?",
            ],
            "recommendations": [
                "What sports equipment and apparel offer the best value for money right now?",
                "Which brands provide reliable athletic gear across multiple sports categories?",
                "What gear would you recommend for someone starting an active fitness routine?",
            ],
            "product_evaluation": [
                "What should buyers evaluate when choosing reliable sports equipment and apparel?",
                "How can athletes test equipment quality and durability before buying?",
            ],
            "comparisons": [
                "How do major sporting goods brands compare on product durability and price accessibility?",
                "What are the key trade-offs between specialized boutique gear and multi-sport equipment?",
            ],
            "audience_specific": [
                "What sporting goods and gear are most recommended for {audience}?",
            ],
            "use_cases": [
                "What sports gear and clothing are recommended for {use_case}?",
            ],
            "pricing_value": [
                "Which sporting goods stores offer the best warranty and return policy on athletic equipment?",
            ],
            "brand_research": [
                "What capabilities distinguish top multi-sport retailers from single-category brands?",
            ],
        },
    },
    "saas_software": {
        "developer_tools": {
            "discovery": [
                "What are the leading modern platforms for {category}?",
                "Which developer tools offer the best developer experience for {category}?",
                "What solutions exist for engineering teams managing {category}?",
                "What are the top open developer platforms for {category}?",
                "How do modern engineering teams approach {category}?",
                "What are the most popular cloud platforms and APIs for {category}?",
            ],
            "recommendations": [
                "Which platform would you recommend for teams implementing {category}?",
                "What infrastructure tools provide the most reliable capabilities for {category}?",
                "Which developer platforms offer the best latency and throughput for {category}?",
                "What is the highest-rated platform for {category} among backend engineers?",
                "Which tools provide seamless API integration for {category}?",
            ],
            "product_evaluation": [
                "What architectural capabilities matter most when evaluating solutions for {category}?",
                "What key trade-offs exist between open-source and managed platforms for {category}?",
                "What latency, uptime, and SLA guarantees should teams look for in {category}?",
                "How should engineering teams evaluate SDK quality and API ergonomics in {category}?",
            ],
            "comparisons": [
                "What are the top alternatives and competitors in {category}?",
                "How do the leading providers in {category} compare on latency, cost, and reliability?",
                "What are the main architectural differences between leading platforms in {category}?",
                "How do hosted cloud gateways compare to self-hosted proxies for {category}?",
            ],
            "audience_specific": [
                "What {category} platforms are best suited for {audience}?",
                "Which developer tools do {audience} recommend for production environments?",
                "How do {audience} evaluate different solutions in {category}?",
            ],
            "use_cases": [
                "What software architecture enables engineering teams to {use_case_base}?",
                "Which platforms help developer teams streamline {use_case}?",
                "What tools are recommended for teams focusing on {use_case}?",
            ],
            "pricing_value": [
                "Which {category} platforms offer transparent usage-based pricing?",
                "What should teams expect to budget for a modern {category} platform?",
                "Which developer tools offer the best performance per dollar in {category}?",
            ],
            "brand_research": [
                "What key differentiators separate top developer platforms in {category}?",
                "What architectural patterns are emerging in {category}?",
            ],
        },
        "general": {
            "discovery": [
                "What are the best modern software solutions for {category}?",
                "Which cloud software platforms are leading the market in {category}?",
                "How do modern organizations approach {category}?",
                "What solutions exist for streamlining {category}?",
                "What are the top-rated software platforms in {category} this year?",
                "Which software platforms provide the most robust foundation for {category}?",
            ],
            "recommendations": [
                "Which software platform would you recommend for growing organizations in {category}?",
                "What are the top recommended tools for managing {category}?",
                "Which platforms offer the most reliable capabilities for {category}?",
                "What software systems provide the highest ROI for {category}?",
                "Which tools would you suggest for scaling {category} workflows?",
            ],
            "product_evaluation": [
                "What security, SOC2, and compliance features should teams evaluate when choosing {category} software?",
                "What features matter most when evaluating enterprise software for {category}?",
                "What are the key integration requirements to look for in {category} platforms?",
                "How should teams evaluate software usability and onboarding in {category}?",
                "What scalability limits should buyers test before committing to a {category} solution?",
            ],
            "comparisons": [
                "What are the key architectural differences between leading platforms in {category}?",
                "How do top software providers in {category} compare on implementation time and ease of use?",
                "What are the main trade-offs between all-in-one suites and specialized tools in {category}?",
                "How do modern cloud tools in {category} compare to legacy on-premise systems?",
            ],
            "audience_specific": [
                "What software platforms in {category} are designed for {audience}?",
                "Which tools do {audience} recommend for {category}?",
                "What capabilities are most essential for {audience} when evaluating {category}?",
                "How do {audience} streamline their operations using modern {category} systems?",
            ],
            "use_cases": [
                "Which software platforms are best suited for {use_case}?",
                "What tools help organizations handle {use_case}?",
                "What solutions enable teams to {use_case_base} with minimal overhead?",
                "How can companies best approach {use_case} using modern platforms?",
            ],
            "pricing_value": [
                "Which {category} solutions offer the most predictable licensing and pricing models?",
                "What should organizations expect to budget for enterprise {category} tools?",
                "Which software tools in {category} offer the best feature set for the cost?",
            ],
            "brand_research": [
                "What capabilities distinguish leading platforms in {category} from legacy software?",
                "What major technology trends are reshaping platforms in {category}?",
                "What should procurement teams look for in long-term roadmaps for {category}?",
            ],
        },
    },
    "ecommerce_retail": {
        "general": {
            "discovery": [
                "What are the best online retailers for quality {category}?",
                "Where can customers find reliable, high-value options for {category}?",
                "What are the top-rated stores and brands for {category}?",
                "What should someone look for when shopping for {category} online?",
            ],
            "recommendations": [
                "Which brands and stores offer the best warranty and return policy for {category}?",
                "What are the top recommended products in {category} for everyday use?",
                "Which retailers provide the most dependable customer service for {category}?",
            ],
            "product_evaluation": [
                "What should customers look for before purchasing {category} online?",
                "What materials and build qualities indicate lasting durability in {category}?",
                "How do customer review ratings correlate with real product quality in {category}?",
            ],
            "comparisons": [
                "How do top retailers compare for pricing transparency and customer support in {category}?",
                "What are the main differences between budget and premium options in {category}?",
            ],
            "audience_specific": [
                "What {category} options are best suited for {audience}?",
            ],
            "use_cases": [
                "What options in {category} are best suited for {use_case}?",
                "How do I select the right {category} for {use_case}?",
            ],
            "pricing_value": [
                "Which stores offer the best value and discount programs for {category}?",
            ],
            "brand_research": [
                "What customer service standards distinguish top retailers in {category}?",
            ],
        },
    },
    "services_professional": {
        "general": {
            "discovery": [
                "How should a business choose a reputable provider for {category}?",
                "What are the top professional firms offering {category}?",
                "What qualifications should clients verify before hiring a firm for {category}?",
            ],
            "recommendations": [
                "Which service providers would you recommend for organizations needing {category}?",
                "What are the highest-rated advisory and service partners in {category}?",
            ],
            "product_evaluation": [
                "What case studies and metrics should clients look for when hiring a firm for {category}?",
                "What scope of service and SLA terms are standard in {category} contracts?",
            ],
            "comparisons": [
                "How do specialized boutique firms compare to large agencies for {category}?",
                "What are the pros and cons of fixed-scope versus retainer models for {category}?",
            ],
            "audience_specific": [
                "What service providers in {category} specialize in working with {audience}?",
            ],
            "use_cases": [
                "What service approach is most effective for {use_case}?",
            ],
            "pricing_value": [
                "What is a standard fee structure and pricing model for {category}?",
            ],
            "brand_research": [
                "What track record and credentials separate top providers in {category}?",
            ],
        },
    },
    "general": {
        "general": {
            "discovery": [
                "What solutions exist for organizations and individuals in {category}?",
                "What are the most reputable providers for {category}?",
                "How should someone evaluate options in {category}?",
                "What are the top choices for someone getting started in {category}?",
                "What leading offerings in {category} provide the best overall experience?",
                "Which options in {category} have the strongest reputation for reliability?",
            ],
            "recommendations": [
                "Which options in {category} offer the best track record and reliability?",
                "What would you recommend for someone getting started in {category}?",
                "What are the top-rated offerings in {category} right now?",
                "Which providers in {category} are most frequently recommended by customers?",
                "What choices in {category} provide the best balance of quality and cost?",
            ],
            "product_evaluation": [
                "What key criteria should someone consider when selecting a solution in {category}?",
                "What features indicate high quality and reliability in {category}?",
                "What are the essential standards and benchmarks to review in {category}?",
                "How do customer reviews and ratings compare across leading {category} options?",
                "What should buyers verify before committing to an option in {category}?",
            ],
            "comparisons": [
                "What are the main differences between standard and advanced options in {category}?",
                "How do leading providers in {category} compare in quality, terms, and support?",
                "What are the trade-offs between established and newer alternatives in {category}?",
                "Which options in {category} provide the greatest long-term satisfaction?",
            ],
            "audience_specific": [
                "What solutions in {category} are most effective for {audience}?",
                "Which options in {category} do {audience} rely on most?",
                "What criteria should {audience} prioritize when looking for {category}?",
                "What are the recommended approaches for {audience} in {category}?",
            ],
            "use_cases": [
                "What solutions are recommended for {use_case}?",
                "How should someone select an option in {category} when {use_case}?",
                "What approaches in {category} work best when focusing on {use_case}?",
                "Which providers specialize in helping clients with {use_case}?",
            ],
            "pricing_value": [
                "What should someone expect to pay for dependable solutions in {category}?",
                "Which options in {category} offer the best value for money?",
                "What pricing models and guarantees are typical in {category}?",
            ],
            "brand_research": [
                "What capabilities distinguish leading organizations in {category}?",
                "What quality factors separate high-end options from budget alternatives in {category}?",
                "What recent developments are changing customer expectations in {category}?",
            ],
        },
    },
    "crm_sales": {
        "crm_sales": {
            "discovery": [
                "What’s a good CRM for a small business?",
                "What are some of the best CRMs for small businesses right now?",
                "What are the most popular CRM platforms for growing businesses?",
                "What solutions exist for managing outbound prospecting and pipeline tracking?",
                "What are the leading sales intelligence and CRM platforms this year?",
                "How do modern B2B sales teams handle lead prospecting and outreach?",
            ],
            "recommendations": [
                "Which CRM is easiest for a small business to get started with?",
                "Which CRM would you recommend for a small business with a limited budget?",
                "What’s a good all-in-one CRM for a small agency?",
                "What are the top CRM choices for a local service business?",
                "Which CRM is worth paying for if you’re a growing team?",
                "What are some simple CRM options for keeping track of customers?",
            ],
            "product_evaluation": [
                "What criteria should sales leaders evaluate when choosing a modern CRM?",
                "What features matter most when selecting outbound sales prospecting software?",
                "How should sales teams evaluate data enrichment accuracy and pipeline tracking?",
                "What integration capabilities should a sales team verify before committing to a CRM?",
            ],
            "comparisons": [
                "I’m looking for a CRM for my small business. Which ones should I compare?",
                "What are the main differences between lightweight CRMs and complex enterprise sales suites?",
                "How do modern outbound sales prospecting platforms compare to traditional CRMs?",
                "What are the key trade-offs between all-in-one CRM platforms and modular sales tools?",
            ],
            "audience_specific": [
                "Which CRM is good for {audience}?",
                "What CRM do {audience} usually choose?",
                "What sales management software is best suited for {audience}?",
                "What CRM platforms do {audience} recommend for managing client relationships?",
            ],
            "use_cases": [
                "What CRM and sales tools are recommended for {use_case}?",
                "Which platforms help sales teams streamline {use_case}?",
                "How do sales teams best handle {use_case} using modern software?",
            ],
            "pricing_value": [
                "What’s an affordable CRM for a small team?",
                "Can you recommend a CRM for a new business that’s trying to keep costs down?",
                "What should a company expect to budget for a modern sales CRM?",
                "Which CRM platforms offer transparent seat and contact pricing?",
            ],
            "brand_research": [
                "What capabilities separate high-velocity sales prospecting platforms from traditional CRMs?",
                "What are the emerging trends in automated sales workflows and CRM data enrichment?",
            ],
        },
    },
    "marketing_automation": {
        "marketing_automation": {
            "discovery": [
                "What are the best marketing automation platforms for growing teams?",
                "What solutions exist for automating email marketing and customer journeys?",
                "Which marketing automation tools are most popular this year?",
                "How do modern marketing teams manage customer segmentation and automated campaigns?",
            ],
            "recommendations": [
                "Which marketing automation platform would you recommend for a B2B company?",
                "What are the top recommended tools for managing automated email campaigns?",
                "Which marketing tools offer the best balance of automation and ease of use?",
            ],
            "product_evaluation": [
                "What features matter most when evaluating marketing automation software?",
                "How should teams evaluate email deliverability and segmentation in marketing tools?",
                "What analytics and attribution features should marketers look for?",
            ],
            "comparisons": [
                "What are the top alternatives and competitors in marketing automation?",
                "How do leading marketing automation tools compare on ease of setup and deliverability?",
            ],
            "audience_specific": [
                "What marketing automation platforms are best suited for {audience}?",
                "Which marketing tools do {audience} recommend for growth campaigns?",
            ],
            "use_cases": [
                "Which platforms are best suited for {use_case}?",
                "What marketing tools help teams streamline {use_case}?",
            ],
            "pricing_value": [
                "Which marketing automation platforms offer transparent contact-based pricing?",
                "What should a company expect to budget for marketing automation software?",
            ],
            "brand_research": [
                "What capabilities separate modern lifecycle marketing tools from basic email senders?",
            ],
        },
    },
    "fintech": {
        "fintech": {
            "discovery": [
                "What are the leading modern payment and billing software platforms?",
                "What solutions exist for automated invoice reconciliation and billing?",
                "Which fintech platforms are most trusted for online payment processing?",
            ],
            "recommendations": [
                "Which payment gateway would you recommend for a subscription business?",
                "What are the top recommended tools for automated invoicing and billing?",
            ],
            "product_evaluation": [
                "What security, PCI compliance, and fraud prevention features should businesses evaluate?",
                "What transaction fee structures and settlement times should businesses compare?",
            ],
            "comparisons": [
                "How do modern subscription billing platforms compare on fee transparency and developer APIs?",
            ],
            "audience_specific": [
                "What billing software is best suited for {audience}?",
            ],
            "use_cases": [
                "What payment platforms are best suited for {use_case}?",
            ],
            "pricing_value": [
                "Which payment platforms offer the most competitive transaction rates?",
            ],
            "brand_research": [
                "What innovations in automated billing and fraud prevention are leading the market?",
            ],
        },
    },
    "healthcare_tech": {
        "healthcare_tech": {
            "discovery": [
                "What are the leading HIPAA-compliant EHR and practice management platforms?",
                "What software exists for modern patient scheduling and clinical workflows?",
            ],
            "recommendations": [
                "Which clinical management software would you recommend for a private practice?",
                "What are the top recommended EHR platforms for clinical teams?",
            ],
            "product_evaluation": [
                "What compliance, HIPAA security, and audit trail capabilities should clinics verify?",
                "How should healthcare providers evaluate patient portal usability and scheduling?",
            ],
            "comparisons": [
                "What are the key differences between cloud-based EHRs and legacy healthcare software?",
            ],
            "audience_specific": [
                "What practice management software is best suited for {audience}?",
            ],
            "use_cases": [
                "What healthcare software is best suited for {use_case}?",
            ],
            "pricing_value": [
                "What is the standard pricing model for clinical EHR and scheduling software?",
            ],
            "brand_research": [
                "What features distinguish modern interoperable healthcare systems from legacy software?",
            ],
        },
    },
    "developer_tools": {
        "developer_tools": {
            "discovery": [
                "What are the leading modern platforms for {category}?",
                "Which developer tools offer the best developer experience for {category}?",
                "What solutions exist for engineering teams managing {category}?",
                "What are the top developer tools and APIs for {category}?",
                "What are the standard developer tools used today for {category}?",
                "How do engineering teams discover dependable solutions for {category}?",
            ],
            "recommendations": [
                "Which platform would you recommend for teams implementing {category}?",
                "What infrastructure tools provide the most reliable capabilities for {category}?",
                "Which developer platforms offer the best latency and throughput for {category}?",
                "What is a recommended developer-friendly solution for {category}?",
                "Which tooling for {category} is most popular among backend developers?",
            ],
            "product_evaluation": [
                "What architectural capabilities matter most when evaluating solutions for {category}?",
                "What latency, uptime, and SLA guarantees should teams look for in {category}?",
                "How should engineering teams evaluate SDK quality and API ergonomics in {category}?",
                "What monitoring, rate-limiting, and error-handling features are crucial in {category}?",
                "What factors should developers check regarding documentation and testing for {category}?",
            ],
            "comparisons": [
                "What are the top alternatives and competitors in {category}?",
                "How do leading providers in {category} compare on latency, cost, and reliability?",
                "What are the key differences between managed services and self-hosted tools in {category}?",
                "How do developers choose between modern API gateways and dedicated routers in {category}?",
            ],
            "audience_specific": [
                "What {category} platforms are best suited for {audience}?",
                "Which developer tools do {audience} recommend for production environments?",
                "What tools in {category} best support the requirements of {audience}?",
                "How do {category} tools handle high-concurrency workloads for {audience}?",
            ],
            "use_cases": [
                "What architecture enables engineering teams to {use_case_base}?",
                "Which platforms help developer teams streamline {use_case}?",
                "What are the recommended tools and practices for {use_case} in production?",
                "How do developers implement reliable fallbacks for {use_case}?",
            ],
            "pricing_value": [
                "Which {category} platforms offer transparent usage-based pricing?",
                "What should teams expect to budget for a modern {category} platform?",
                "How do per-request and token pricing tiers compare across {category} tools?",
                "Which platforms in {category} provide generous free tiers or test credits for developers?",
            ],
            "brand_research": [
                "What key differentiators separate top developer platforms in {category}?",
                "What technical innovations are advancing modern architectures in {category}?",
                "Why are engineering teams migrating to next-generation tools in {category}?",
            ],
        },
    },
    "general_business_software": {
        "general_business_software": {
            "discovery": [
                "What are the best modern software solutions for {category}?",
                "Which cloud software platforms are leading the market in {category}?",
                "What solutions exist for streamlining {category}?",
                "What are popular tools for teams looking to improve {category}?",
                "What are the top software platforms available today for {category}?",
                "How do modern businesses approach managing {category}?",
            ],
            "recommendations": [
                "Which software platform would you recommend for growing organizations in {category}?",
                "What are the top recommended tools for managing {category}?",
                "What is a reliable, user-friendly platform for {category}?",
                "Which software solution in {category} offers the best balance of power and simplicity?",
                "What tools would you suggest for a team standardizing their {category} workflows?",
                "Which software in {category} is most widely adopted by high-growth companies?",
            ],
            "product_evaluation": [
                "What security, SOC2, and compliance features should teams evaluate in {category} software?",
                "What features matter most when evaluating enterprise software for {category}?",
                "What capabilities should product teams prioritize when selecting a {category} tool?",
                "How do different software architectures impact performance and reliability in {category}?",
                "What integration support is essential when rolling out a new system for {category}?",
            ],
            "comparisons": [
                "What are the key trade-offs between leading platforms in {category}?",
                "How do modern next-generation tools in {category} compare to legacy enterprise suites?",
                "What are the pros and cons of specialized tools versus all-in-one software for {category}?",
                "When comparing platforms for {category}, what hidden costs or limitations should buyers watch for?",
                "How do usability and speed differ among top platforms in {category}?",
            ],
            "audience_specific": [
                "What software platforms in {category} are designed for {audience}?",
                "Which solutions in {category} best support {audience}?",
                "What tools in {category} do {audience} typically prefer?",
                "How do solutions in {category} accommodate the specific workflow needs of {audience}?",
            ],
            "use_cases": [
                "Which software platforms are best suited for {use_case}?",
                "What tools provide the best support when managing {use_case}?",
                "How can teams optimize {use_case} using modern {category} platforms?",
                "What are the most effective workflows for {use_case} in {category}?",
            ],
            "pricing_value": [
                "What should organizations expect to budget for modern {category} tools?",
                "Which software options in {category} offer transparent, scalable pricing?",
                "What are typical per-user or consumption pricing models in {category}?",
                "Which tools in {category} deliver the fastest return on investment?",
            ],
            "brand_research": [
                "What capabilities distinguish leading platforms in {category} from legacy software?",
                "What technical innovations are currently shaping the future of {category}?",
                "What quality factors separate premium platforms from basic utilities in {category}?",
                "Why are fast-growing companies switching platforms in {category}?",
            ],
        },
    },
    "uncertain_category": {
        "uncertain_category": {
            "discovery": [
                "What solutions exist for organizations looking for {category}?",
                "What are the most reputable providers for {category}?",
                "What are the top choices for someone getting started in {category}?",
                "What options are available today for {category}?",
                "How do organizations typically evaluate available providers in {category}?",
                "What are the standard approaches to handling {category}?",
            ],
            "recommendations": [
                "Which options in {category} offer the best track record and reliability?",
                "What would you recommend for someone getting started in {category}?",
                "Which providers in {category} have the strongest reputation for customer satisfaction?",
                "What is a dependable solution to consider for {category}?",
                "Which provider in {category} is known for high service quality and consistency?",
            ],
            "product_evaluation": [
                "What key criteria should someone consider when selecting a solution in {category}?",
                "What features indicate high quality and reliability in {category}?",
                "What questions should a buyer ask before choosing a provider in {category}?",
                "What performance or service benchmarks matter most in {category}?",
            ],
            "comparisons": [
                "How do leading providers in {category} compare in quality and terms?",
                "What are the main differences between premium and entry-level options in {category}?",
                "What trade-offs should someone evaluate when comparing choices in {category}?",
                "How do independent reviews rank the top options in {category}?",
            ],
            "audience_specific": [
                "What solutions in {category} are most effective for {audience}?",
                "Which providers in {category} cater specifically to {audience}?",
                "What options in {category} best address the constraints faced by {audience}?",
            ],
            "use_cases": [
                "What solutions are recommended for {use_case}?",
                "Which options in {category} work best when addressing {use_case}?",
                "What is the standard approach to solving {use_case} in this category?",
            ],
            "pricing_value": [
                "What should someone expect to pay for dependable solutions in {category}?",
                "What pricing structures are typical across providers in {category}?",
                "Which options in {category} provide the best overall value for the cost?",
            ],
            "brand_research": [
                "What quality factors separate high-end options from budget alternatives in {category}?",
                "What standards distinguish trustworthy providers from unvetted options in {category}?",
                "What recent trends or changes are affecting buyers in {category}?",
            ],
        },
    },
}


class TemplateRegistry:
    """Selects and manages grounded prompt templates for classified profiles."""

    @classmethod
    def get_templates_for_archetype(
        cls,
        archetype: str,
        subcategory: Optional[str] = None
    ) -> Dict[str, List[str]]:
        arch_key = archetype
        if archetype in ("footwear_apparel", "sportswear_sporting_goods"):
            arch_key = "sportswear_sporting_goods"
        elif archetype == "crm_sales":
            arch_key = "crm_sales"
        elif archetype == "marketing_automation":
            arch_key = "marketing_automation"
        elif archetype == "fintech":
            arch_key = "fintech"
        elif archetype == "healthcare_tech":
            arch_key = "healthcare_tech"
        elif archetype in ("developer_tools", "developer_infrastructure"):
            arch_key = "developer_tools"
        elif archetype in ("saas_software",):
            if subcategory == "developer_tools":
                arch_key = "developer_tools"
            else:
                arch_key = "general_business_software"
        elif archetype == "general_business_software":
            arch_key = "general_business_software"
        elif archetype == "uncertain_category":
            arch_key = "uncertain_category"
        elif archetype in ("enterprise_saas", "creative_tools"):
            arch_key = "developer_tools"
        elif archetype in ("ecommerce_retail", "consumer_ecommerce"):
            arch_key = "ecommerce_retail"
        elif archetype in ("services_professional", "professional_services"):
            arch_key = "services_professional"

        arch_dict = CATEGORY_TEMPLATES.get(arch_key, CATEGORY_TEMPLATES.get(archetype, CATEGORY_TEMPLATES["general"]))
        if subcategory and subcategory in arch_dict:
            return arch_dict[subcategory]
        if "general" in arch_dict:
            return arch_dict["general"]
        first_sub = next(iter(arch_dict.values()))
        return first_sub

    @classmethod
    def get_template_version(cls) -> str:
        return TEMPLATE_SYSTEM_VERSION

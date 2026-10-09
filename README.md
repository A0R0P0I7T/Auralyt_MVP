# Auralyt — Engine 1: Brand & Website Profiler

Engine 1 is the foundational ground-truth intelligence layer of the **Auralyt** platform. It crawls accessible website pages, extracts structured metadata, cleans readable content, synthesizes a verifiable brand profile, and provides a human-in-the-loop review workflow.

Its outputs serve as the immutable source of truth for downstream engines (such as **Engine 2: Prompt Intelligence**).

---

## 🏛️ Architecture Overview

```
                                 [ Website URL Input ]
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │         SSRF & DNS Security Guard         │
                     │  - Rejects loopback & private IPv4/IPv6   │
                     │  - Blocks cloud metadata endpoints        │
                     │  - Enforces HTTP/HTTPS scheme & bounds    │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │          Robots & Sitemap Discoverer      │
                     │  - Respects robots.txt directives         │
                     │  - Parses XML sitemaps & indexes          │
                     │  - Prioritizes high-value brand URLs      │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │        Scrapling Crawler Engine           │
                     │  - AsyncFetcher (HTTP/2 / TLS fingerprints)│
                     │  - Politeness delays & concurrency bounds │
                     │  - DynamicFetcher fallback for JS-only    │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │      Page Extraction & Normalization      │
                     │  - Strips boilerplate (nav, footer, ads)  │
                     │  - Parses JSON-LD Schema.org graphs       │
                     │  - Extracts OpenGraph, Twitter, headings  │
                     │  - Classifies page type & extracts links  │
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │       Brand Fact Synthesizer              │
                     │  - Extracts products, use cases, audience │
                     │  - Tracks provenance & source URL/snippet │
                     │  - Assigns confidence & default unverified│
                     └─────────────────────┬─────────────────────┘
                                           │
                                           ▼
                     ┌───────────────────────────────────────────┐
                     │      Human Verification & Persistence     │
                     │  - Review, edit, confirm, or add facts    │
                     │  - Confirmed facts protected across runs  │
                     │  - Versioned brand profile store          │
                     └───────────────────────────────────────────┘
```

---

## 🚀 Key Features

1. **Scrapling Crawling Engine**: Built on Scrapling `AsyncFetcher` with bounded per-host concurrency, politeness delays, bounded crawl depth (max 3), and page limits (default 30, max 50).
2. **Strict SSRF & Crawler Safety**:
   - Blocks private IPv4 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`).
   - Blocks private/local IPv6 (`::1`, `fc00::/7`, `fe80::/10`).
   - Explicitly blocks AWS/Azure/GCP metadata endpoints (`169.254.169.254`, `metadata.google.internal`, `instance-data`).
   - Re-resolves redirect destination IPs to prevent redirect-based SSRF pivoting.
3. **Robots.txt & Sitemap Discovery**:
   - Parses `robots.txt` using standard directives and custom crawl delays.
   - Discovers XML sitemaps, recursive sitemap indexes, and gzipped sitemaps.
   - Prioritizes high-value business pages (`/about`, `/pricing`, `/products`, `/solutions`, `/features`).
4. **Boilerplate-Stripped Extraction**:
   - Removes navigation headers, footer links, cookie banners, consent modals, and script tags.
   - Extracts clean readable text, markdown structure, OpenGraph/Twitter cards, and Schema.org JSON-LD structured data.
5. **Deterministic Brand Fact Synthesis with Provenance**:
   - Extracts business name, company description, products & services, features, target audience, use cases, public pricing, FAQs, and contact info.
   - Every fact retains:
     - `source_url`
     - `source_page_id`
     - `evidence_snippet`
     - `extraction_method` (e.g., `json_ld_schema`, `meta_description`, `heading_heuristic`, `user_input`)
     - `confidence` (0.0 to 1.0)
     - `user_confirmed` (boolean)
6. **Human Verification Layer**:
   - Allows users to review, confirm, edit, or delete automatically extracted facts.
   - Users can manually add ground-truth facts.
   - **Protection against silent overwrites**: User-confirmed facts are permanently retained and preserved during subsequent crawl refreshes.
   - Profile versions (`profile_version`) are tracked for downstream consumers.
7. **Interactive Dashboard**:
   - Responsive web dashboard available directly at `http://localhost:8000/`.
   - Live progress monitor with status badges, discovered/processed counts, and warning banners.
   - Evidence inspector modal displaying source URLs and highlighted supporting text snippets.

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, FastAPI, Pydantic v2, Pydantic-Settings
- **Crawler**: Scrapling (with `curl_cffi`, `AsyncFetcher`, `DynamicFetcher`, `browserforge`, `protego`)
- **Parsing**: BeautifulSoup4, lxml, markdownify
- **Database**: SQLite (via `aiosqlite` for zero-configuration local development) or PostgreSQL (`asyncpg`)
- **ORM & Migrations**: SQLAlchemy 2.0 (async), Alembic
- **Testing**: Pytest, Pytest-Asyncio, HTTPX

---

## 📦 Installation & Setup

### 1. Clone repository & initialize virtual environment
```bash
python -m venv venv

# Windows PowerShell:
.\venv\Scripts\Activate.ps1

# Linux/macOS:
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Apply database migrations
```bash
alembic upgrade head
```

### 4. Run the development server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at:
- **Interactive Dashboard**: [http://localhost:8000/](http://localhost:8000/)
- **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Running the Test Suite

Run all unit and integration tests:
```bash
pytest tests -v
```

Run the end-to-end demonstration script:
```bash
python scripts/demo_profiler.py
```

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/brands/profile` | Onboard website URL and initiate asynchronous profiling run |
| `GET` | `/api/brands/profile-runs/{run_id}` | Fetch status, metrics, and warnings for a crawl run |
| `GET` | `/api/brands/{brand_id}/profile` | Retrieve synthesized brand profile, evidence, and facts |
| `GET` | `/api/brands/{brand_id}` | Get brand entity details |
| `PATCH` | `/api/brands/{brand_id}` | Update brand metadata (name, industry, market, language) |
| `GET` | `/api/brands/{brand_id}/pages` | Retrieve crawled pages with pagination (`page`, `page_size`, `page_type`) |
| `GET` | `/api/brands/{brand_id}/pages/{page_id}` | Retrieve detailed single crawled page with headings and raw text |
| `GET` | `/api/brands/{brand_id}/facts` | List all facts with provenance, confidence, and verification status |
| `POST` | `/api/brands/{brand_id}/facts` | Add a manual ground-truth fact |
| `PATCH` | `/api/brands/{brand_id}/facts/{fact_id}` | Edit fact value or toggle `user_confirmed` |
| `DELETE` | `/api/brands/{brand_id}/facts/{fact_id}` | Delete a fact from the brand profile |
| `POST` | `/api/brands/{brand_id}/profile-runs` | Trigger a profile refresh (increments version, preserves confirmed facts) |
| `GET` | `/api/brands/{brand_id}/profile-runs` | View profiling history |

---

## 🔗 Handoff Contract: Consumption by Engine 2 (Prompt Intelligence)

Engine 2 can retrieve the complete, verified brand profile via:
`GET /api/brands/{brand_id}/profile`

The response payload is strictly structured and self-contained:
```json
{
  "brand": {
    "id": "595cd51e-8375-467e-9b3f-9ed60e14e688",
    "domain": "example.com",
    "business_name": "Example Domain Inc.",
    "industry": "Internet Standards",
    "target_market": "Global",
    "profile_version": 1
  },
  "business_overview": {
    "business_name": "Example Domain Inc.",
    "domain": "example.com",
    "industry": "Internet Standards",
    "description": "Example Domain is provided for illustrative examples in documents."
  },
  "products_and_services": [
    {
      "fact_id": "fact-1",
      "value": "Reserved illustrative domain names",
      "provenance": "https://example.com/",
      "snippet": "As specified in RFC 2606...",
      "confirmed": true,
      "confidence": 1.0
    }
  ],
  "target_audience": [...],
  "use_cases": [...],
  "pricing_information": [...],
  "faqs": [...],
  "facts": [...],
  "coverage_summary": {
    "total_pages_crawled": 1,
    "total_facts_extracted": 4,
    "profile_status": "completed"
  },
  "verification_progress": {
    "total_facts": 4,
    "confirmed_facts": 4,
    "verification_rate": 1.0
  }
}
```
Engine 2 uses these verified brand facts as prompt input anchors without ever needing to crawl the web or query the database directly.

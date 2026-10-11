import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(test_db_session):
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_proxy():
    yield
    from app.crawler.transport import stop_local_proxy
    await stop_local_proxy()


@pytest_asyncio.fixture
async def profiled_brand(test_db_session):
    """Fixture providing an onboarded brand with verified facts."""
    from app.db.models import Brand, ProfileRun, BrandFact

    brand = Brand(
        domain="aurora-ai.io",
        business_name="Aurora AI",
        industry="Artificial Intelligence",
        target_market="Global",
        language="en",
        profile_version=1,
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        status="completed",
        page_limit=10,
        pages_discovered=5,
        pages_succeeded=5,
    )
    test_db_session.add(run)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="business_overview",
            fact_value={"description": "Autonomous AI workflow optimization platform."},
            confidence=0.95,
            user_confirmed=True,
            source_url="https://aurora-ai.io/about",
            evidence_snippet="Aurora AI accelerates enterprise agent orchestration.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value={"name": "Aurora Agent Flow"},
            confidence=0.90,
            user_confirmed=True,
            source_url="https://aurora-ai.io/products",
            evidence_snippet="Aurora Agent Flow orchestrates multi-agent tasks.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value={"segment": "AI Engineers and Product Managers"},
            confidence=0.88,
            user_confirmed=False,
            source_url="https://aurora-ai.io/solutions",
            evidence_snippet="Built for AI engineers building production pipelines.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="pricing",
            fact_value={"model": "Developer Free Tier and Enterprise Scale"},
            confidence=0.85,
            user_confirmed=True,
            source_url="https://aurora-ai.io/pricing",
            evidence_snippet="Flexible developer and enterprise tiers.",
        ),
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()
    await test_db_session.refresh(brand)
    return brand


import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import Brand, ProfileRun, CrawledPage, BrandFact
from app.schemas.brand import BrandOnboardRequest, BrandResponse, BrandUpdateRequest
from app.schemas.profile_run import ProfileRunResponse, ProfileRunCreateRequest
from app.schemas.crawled_page import CrawledPageResponse, CrawledPageListItem, CrawledPageListResponse
from app.schemas.brand_fact import BrandFactResponse, BrandFactCreateRequest, BrandFactUpdateRequest
from app.schemas.profile_summary import ProfileSummaryResponse
from app.crawler.security import SecurityValidationError
from app.services.profiler_service import ProfilerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brands", tags=["Brands & Profiling"])


@router.get(
    "",
    response_model=List[BrandResponse],
    summary="List all onboarded brands"
)
async def list_brands(
    db: AsyncSession = Depends(get_db)
):
    """List all onboarded brands ordered by creation date."""
    stmt = select(Brand).order_by(desc(Brand.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post(
    "/profile",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Onboard website and initiate brand profiling run"
)
async def onboard_and_profile_brand(
    payload: BrandOnboardRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Accepts website URL, validates domain/SSRF safety, registers brand,
    and initiates asynchronous crawling and fact profiling.
    """
    try:
        brand, run = await ProfilerService.onboard_brand(
            website_url=payload.website_url,
            business_name=payload.business_name,
            industry=payload.industry,
            target_market=payload.target_market,
            language=payload.language,
            page_limit=payload.page_limit or 30,
            db=db
        )
        return {
            "message": "Profiling initiated successfully.",
            "brand_id": brand.id,
            "run_id": run.id,
            "status": run.status,
            "domain": brand.domain,
            "status_check_url": f"/api/brands/profile-runs/{run.id}",
            "profile_url": f"/api/brands/{brand.id}/profile"
        }
    except SecurityValidationError as se:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security/URL validation error: {str(se)}"
        )
    except Exception as e:
        logger.exception("Failed to initiate profiling")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate profiling due to an internal error."
        )


@router.get(
    "/profile-runs/{run_id}",
    response_model=ProfileRunResponse,
    summary="Get status and progress of a profiling run"
)
async def get_profile_run(
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    run = await db.get(ProfileRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="ProfileRun not found.")
    return run


@router.get(
    "/{brand_id}/profile",
    response_model=ProfileSummaryResponse,
    summary="Get current structured brand profile and evidence"
)
async def get_brand_profile(
    brand_id: str,
    db: AsyncSession = Depends(get_db)
):
    profile = await ProfilerService.get_brand_profile_summary(brand_id, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Brand not found.")
    return profile


@router.get(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Get brand details"
)
async def get_brand(
    brand_id: str,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")
    return brand


@router.patch(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Update brand general information"
)
async def update_brand(
    brand_id: str,
    payload: BrandUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")
    
    if payload.business_name is not None:
        brand.business_name = payload.business_name
    if payload.industry is not None:
        brand.industry = payload.industry
    if payload.target_market is not None:
        brand.target_market = payload.target_market
    if payload.language is not None:
        brand.language = payload.language

    await db.commit()
    await db.refresh(brand)
    return brand


@router.get(
    "/{brand_id}/pages",
    response_model=CrawledPageListResponse,
    summary="Get crawled pages with pagination and filtering"
)
async def get_crawled_pages(
    brand_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(15, ge=1, le=100, description="Items per page"),
    page_type: Optional[str] = Query(None, description="Filter by page type"),
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    base_query = select(CrawledPage).where(CrawledPage.brand_id == brand_id)
    if page_type:
        base_query = base_query.where(CrawledPage.page_type == page_type)

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total_res = await db.execute(count_query)
    total = total_res.scalar_one()

    # Fetch page with fact counts
    offset = (page - 1) * page_size
    items_query = (
        select(CrawledPage, func.count(BrandFact.id).label("facts_count"))
        .outerjoin(BrandFact, CrawledPage.id == BrandFact.source_page_id)
        .where(CrawledPage.brand_id == brand_id)
    )
    if page_type:
        items_query = items_query.where(CrawledPage.page_type == page_type)

    items_query = (
        items_query.group_by(CrawledPage.id)
        .order_by(CrawledPage.fetched_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items_res = await db.execute(items_query)
    rows = items_res.all()

    page_items = []
    for cp, f_cnt in rows:
        item = CrawledPageListItem(
            id=cp.id,
            requested_url=cp.requested_url,
            final_url=cp.final_url,
            http_status=cp.http_status,
            title=cp.title,
            page_type=cp.page_type,
            extraction_status=cp.extraction_status,
            fetched_at=cp.fetched_at,
            used_js=cp.used_js,
            facts_count=f_cnt or 0
        )
        page_items.append(item)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return CrawledPageListResponse(
        items=page_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get(
    "/{brand_id}/pages/{page_id}",
    response_model=CrawledPageResponse,
    summary="Get single crawled page full details"
)
async def get_crawled_page_detail(
    brand_id: str,
    page_id: str,
    db: AsyncSession = Depends(get_db)
):
    page = await db.get(CrawledPage, page_id)
    if not page or page.brand_id != brand_id:
        raise HTTPException(status_code=404, detail="Crawled page not found.")

    facts_stmt = select(BrandFact).where(BrandFact.source_page_id == page_id)
    facts_res = await db.execute(facts_stmt)
    facts = facts_res.scalars().all()

    page_dict = {col.name: getattr(page, col.name) for col in page.__table__.columns}
    page_dict["extracted_facts"] = [
        {
            "id": f.id,
            "fact_type": f.fact_type,
            "fact_value": f.fact_value,
            "confidence": f.confidence,
            "user_confirmed": f.user_confirmed,
            "is_rejected": f.is_rejected,
            "evidence_snippet": f.evidence_snippet
        }
        for f in facts
    ]
    return CrawledPageResponse(**page_dict)


@router.get(
    "/{brand_id}/facts",
    response_model=List[BrandFactResponse],
    summary="List all facts for a brand"
)
async def get_brand_facts(
    brand_id: str,
    fact_type: Optional[str] = Query(None, description="Filter by fact type"),
    status: Optional[str] = Query(None, description="Filter by status: confirmed, pending, rejected"),
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    query = select(BrandFact).where(BrandFact.brand_id == brand_id)
    if fact_type:
        query = query.where(BrandFact.fact_type == fact_type)
    if status == "confirmed":
        query = query.where(BrandFact.user_confirmed == True, BrandFact.is_rejected == False)
    elif status == "rejected":
        query = query.where(BrandFact.is_rejected == True)
    elif status == "pending":
        query = query.where(BrandFact.user_confirmed == False, BrandFact.is_rejected == False)
    
    query = query.order_by(desc(BrandFact.user_confirmed), desc(BrandFact.confidence))
    res = await db.execute(query)
    return res.scalars().all()


@router.post(
    "/{brand_id}/facts",
    response_model=BrandFactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a confirmed fact to the brand profile"
)
async def create_brand_fact(
    brand_id: str,
    payload: BrandFactCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    fact_source_url = None
    if payload.source_url:
        s_url = payload.source_url.strip()
        from urllib.parse import urlparse, urlunparse
        try:
            parsed_s = urlparse(s_url)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_url is malformed."
            )
        if parsed_s.scheme.lower() not in ("http", "https") or not parsed_s.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_url must be an HTTP or HTTPS URL with a valid hostname."
            )
        clean_netloc = parsed_s.netloc.split("@")[-1]
        source_host = (clean_netloc.split(":")[0] or "").lower().rstrip(".")
        brand_host = brand.domain.lower().removeprefix("www.").rstrip(".")
        if source_host != brand_host and not source_host.endswith("." + brand_host):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_url must belong to the profiled brand domain.",
            )
        fact_source_url = urlunparse((parsed_s.scheme.lower(), clean_netloc, parsed_s.path, parsed_s.params, parsed_s.query, ""))

    fact = BrandFact(
        brand_id=brand_id,
        profile_version=brand.profile_version,
        fact_type=payload.fact_type,
        fact_value=payload.fact_value,
        source_url=fact_source_url,
        evidence_snippet=payload.evidence_snippet or "Manually added by user",
        extraction_method="user_input",
        confidence=payload.confidence,
        user_confirmed=payload.user_confirmed
    )
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return fact


@router.patch(
    "/{brand_id}/facts/{fact_id}",
    response_model=BrandFactResponse,
    summary="Edit, confirm, or verify a brand fact"
)
async def update_brand_fact(
    brand_id: str,
    fact_id: str,
    payload: BrandFactUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    fact = await db.get(BrandFact, fact_id)
    if not fact or fact.brand_id != brand_id:
        raise HTTPException(status_code=404, detail="BrandFact not found.")

    if payload.fact_value is not None:
        fact.fact_value = payload.fact_value
    if payload.user_confirmed is not None:
        fact.user_confirmed = payload.user_confirmed
        if payload.user_confirmed:
            fact.is_rejected = False
    if payload.is_rejected is not None:
        fact.is_rejected = payload.is_rejected
        if payload.is_rejected:
            fact.user_confirmed = False

    await db.commit()
    await db.refresh(fact)
    return fact


@router.delete(
    "/{brand_id}/facts/{fact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a fact from the brand profile"
)
async def delete_brand_fact(
    brand_id: str,
    fact_id: str,
    db: AsyncSession = Depends(get_db)
):
    fact = await db.get(BrandFact, fact_id)
    if not fact or fact.brand_id != brand_id:
        raise HTTPException(status_code=404, detail="BrandFact not found.")

    await db.delete(fact)
    await db.commit()
    return None


@router.post(
    "/{brand_id}/profile-runs",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a profiling refresh run for an existing brand"
)
async def refresh_brand_profile(
    brand_id: str,
    payload: ProfileRunCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    # Increment profile version for fresh crawl
    brand.profile_version += 1

    run = ProfileRun(
        brand_id=brand.id,
        profile_version=brand.profile_version,
        status="pending",
        page_limit=payload.page_limit or 30
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    start_url = f"https://{brand.domain}"
    from app.services.profiler_service import ProfilerService
    import asyncio
    asyncio.create_task(ProfilerService.execute_profile_run(run.id, start_url))

    return {
        "message": "Profile refresh initiated.",
        "brand_id": brand.id,
        "run_id": run.id,
        "profile_version": brand.profile_version,
        "status_check_url": f"/api/brands/profile-runs/{run.id}"
    }


@router.get(
    "/{brand_id}/profile-runs",
    response_model=List[ProfileRunResponse],
    summary="View profiling run history for a brand"
)
async def list_brand_profile_runs(
    brand_id: str,
    db: AsyncSession = Depends(get_db)
):
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found.")

    stmt = select(ProfileRun).where(ProfileRun.brand_id == brand_id).order_by(desc(ProfileRun.started_at))
    res = await db.execute(stmt)
    return res.scalars().all()

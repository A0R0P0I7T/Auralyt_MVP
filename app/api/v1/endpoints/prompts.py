"""API Endpoints for Engine 2: Prompt Intelligence."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import PromptRun, PromptCandidate, User, Organization
from app.schemas.prompt import (
    PromptGenerateRequest,
    PromptRunResponse,
    PromptCandidateResponse,
    PromptUpdateRequest,
    PromptReviewRequest,
    PromptBatchReviewRequest,
    PromptListResponse,
    PromptCoverageSummary,
)
from app.prompts.service import PromptIntelligenceService
from app.auth.dependencies import get_current_user, get_current_org, verify_brand_access

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engine 2: Prompt Intelligence"])


@router.post(
    "/brands/{brand_id}/prompts/generate",
    response_model=dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start prompt intelligence generation for a brand"
)
async def generate_prompts(
    brand_id: str,
    payload: PromptGenerateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Consumes Engine 1's ground-truth profile and generates a structured,
    grounded collection of evaluation prompts across search intents and buying stages.
    """
    await verify_brand_access(brand_id, db, current_org)

    try:
        run, prompts = await PromptIntelligenceService.generate_prompts(
            brand_id=brand_id,
            prompt_count=payload.prompt_count,
            categories=payload.categories,
            language=payload.language,
            force_regenerate=payload.force_regenerate,
            db=db
        )
        diagnostics = (run.config_metadata or {}).get("diagnostics", {})
        return {
            "message": "Prompt intelligence generation completed successfully.",
            "run_id": run.id,
            "brand_id": brand_id,
            "status": run.status,
            "prompts_generated": len(prompts),
            "profile_version": run.profile_version,
            "diagnostics": diagnostics,
            "run_check_url": f"/api/brands/{brand_id}/prompts/runs/{run.id}",
            "prompts_url": f"/api/brands/{brand_id}/prompts"
        }
    except ValueError as ve:
        err_msg = str(ve)
        if "Brand not found" in err_msg:
            raise HTTPException(status_code=404, detail="Brand not found.")
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        logger.exception(f"Prompt generation error for brand {brand_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate prompts due to an internal error."
        )


@router.get(
    "/brands/{brand_id}/prompts/runs/{run_id}",
    response_model=PromptRunResponse,
    summary="Get status and details of a prompt generation run"
)
async def get_prompt_run(
    brand_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    await verify_brand_access(brand_id, db, current_org)

    run = await db.get(PromptRun, run_id)
    if not run or run.brand_id != brand_id:
        raise HTTPException(status_code=404, detail="Prompt run not found.")
    return run


@router.get(
    "/brands/{brand_id}/prompts",
    response_model=PromptListResponse,
    summary="List and filter generated prompts for a brand"
)
async def list_brand_prompts(
    brand_id: str,
    category: Optional[str] = Query(None, description="Filter by category"),
    intent: Optional[str] = Query(None, description="Filter by search intent"),
    is_approved: Optional[bool] = Query(None, description="Filter by approval status"),
    lifecycle_status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    is_archived: bool = Query(False, description="Filter archived prompts"),
    search: Optional[str] = Query(None, description="Search prompt text"),
    profile_version: Optional[int] = Query(None, description="Filter by specific profile version"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    await verify_brand_access(brand_id, db, current_org)

    try:
        res = await PromptIntelligenceService.list_prompts(
            brand_id=brand_id,
            category=category,
            intent=intent,
            is_approved=is_approved,
            lifecycle_status=lifecycle_status,
            is_archived=is_archived,
            search=search,
            profile_version=profile_version,
            page=page,
            page_size=page_size,
            db=db
        )
        return PromptListResponse(**res)
    except ValueError as ve:
        if "Brand not found" in str(ve):
            raise HTTPException(status_code=404, detail="Brand not found.")
        raise HTTPException(status_code=400, detail=str(ve))


@router.get(
    "/brands/{brand_id}/prompts/coverage",
    response_model=PromptCoverageSummary,
    summary="Get intent and category coverage summary for brand prompts"
)
async def get_prompt_coverage(
    brand_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    await verify_brand_access(brand_id, db, current_org)

    try:
        data = await PromptIntelligenceService.get_coverage_summary(brand_id, db)
        return PromptCoverageSummary(**data)
    except ValueError as ve:
        if "Brand not found" in str(ve):
            raise HTTPException(status_code=404, detail="Brand not found.")
        raise HTTPException(status_code=400, detail=str(ve))


@router.get(
    "/prompts/{prompt_id}",
    response_model=PromptCandidateResponse,
    summary="Get full details, provenance, and scores for a prompt"
)
async def get_prompt_detail(
    prompt_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    prompt = await PromptIntelligenceService.get_prompt(prompt_id, db)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    # Enforce tenant boundary on associated brand
    await verify_brand_access(prompt.brand_id, db, current_org)
    return prompt


@router.patch(
    "/prompts/{prompt_id}",
    response_model=PromptCandidateResponse,
    summary="Edit prompt text, toggle approval, or archive"
)
async def update_prompt(
    prompt_id: str,
    payload: PromptUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    prompt = await PromptIntelligenceService.get_prompt(prompt_id, db)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")

    # Enforce tenant boundary on associated brand
    await verify_brand_access(prompt.brand_id, db, current_org)

    try:
        updated = await PromptIntelligenceService.update_prompt(
            prompt_id=prompt_id,
            text=payload.text,
            is_approved=payload.is_approved,
            is_archived=payload.is_archived,
            db=db
        )
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.put(
    "/brands/{brand_id}/prompts/{prompt_id}/review",
    response_model=PromptCandidateResponse,
    summary="Review a prompt: approve, reject, edit text, or add notes"
)
async def review_prompt(
    brand_id: str,
    prompt_id: str,
    payload: PromptReviewRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    await verify_brand_access(brand_id, db, current_org)

    try:
        updated = await PromptIntelligenceService.review_prompt(
            brand_id=brand_id,
            prompt_id=prompt_id,
            lifecycle_status=payload.lifecycle_status,
            text=payload.text,
            review_notes=payload.review_notes,
            db=db
        )
        return updated
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post(
    "/brands/{brand_id}/prompts/batch-review",
    response_model=List[PromptCandidateResponse],
    summary="Batch review multiple prompts for a brand"
)
async def batch_review_prompts(
    brand_id: str,
    payload: PromptBatchReviewRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    await verify_brand_access(brand_id, db, current_org)

    try:
        updated_list = await PromptIntelligenceService.batch_review_prompts(
            brand_id=brand_id,
            prompt_ids=payload.prompt_ids,
            lifecycle_status=payload.lifecycle_status,
            review_notes=payload.review_notes,
            db=db
        )
        return updated_list
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

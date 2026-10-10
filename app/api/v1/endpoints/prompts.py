"""API Endpoints for Engine 2: Prompt Intelligence."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import PromptRun
from app.schemas.prompt import (
    PromptGenerateRequest,
    PromptRunResponse,
    PromptCandidateResponse,
    PromptUpdateRequest,
    PromptListResponse,
    PromptCoverageSummary,
)
from app.prompts.service import PromptIntelligenceService

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
    db: AsyncSession = Depends(get_db)
):
    """
    Consumes Engine 1's ground-truth profile and generates a structured,
    grounded collection of evaluation prompts across search intents and buying stages.
    """
    try:
        run, prompts = await PromptIntelligenceService.generate_prompts(
            brand_id=brand_id,
            prompt_count=payload.prompt_count,
            categories=payload.categories,
            language=payload.language,
            force_regenerate=payload.force_regenerate,
            db=db
        )
        return {
            "message": "Prompt intelligence generation completed successfully.",
            "run_id": run.id,
            "brand_id": brand_id,
            "status": run.status,
            "prompts_generated": len(prompts),
            "profile_version": run.profile_version,
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
    db: AsyncSession = Depends(get_db)
):
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
    is_archived: bool = Query(False, description="Filter archived prompts"),
    search: Optional[str] = Query(None, description="Search prompt text"),
    profile_version: Optional[int] = Query(None, description="Filter by specific profile version"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    try:
        res = await PromptIntelligenceService.list_prompts(
            brand_id=brand_id,
            category=category,
            intent=intent,
            is_approved=is_approved,
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
    db: AsyncSession = Depends(get_db)
):
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
    db: AsyncSession = Depends(get_db)
):
    prompt = await PromptIntelligenceService.get_prompt(prompt_id, db)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    return prompt


@router.patch(
    "/prompts/{prompt_id}",
    response_model=PromptCandidateResponse,
    summary="Edit prompt text, toggle approval, or archive"
)
async def update_prompt(
    prompt_id: str,
    payload: PromptUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    prompt = await PromptIntelligenceService.update_prompt(
        prompt_id=prompt_id,
        text=payload.text,
        is_approved=payload.is_approved,
        is_archived=payload.is_archived,
        db=db
    )
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found.")
    return prompt

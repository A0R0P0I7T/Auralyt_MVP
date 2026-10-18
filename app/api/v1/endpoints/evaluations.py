"""API Endpoints for Engine 3: AI Visibility Evaluator."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import User, Organization
from app.schemas.evaluator import (
    VisibilityScanCreateRequest,
    VisibilityScanResponse,
    VisibilityResultResponse,
    VisibilityScanDetailResponse,
    VisibilityScanListResponse,
)
from app.evaluator.service import VisibilityEvaluatorService
from app.schemas.diagnosis import DiagnosisReport
from app.services.diagnosis_service import VisibilityDiagnosisService
from app.auth.dependencies import get_current_user, get_current_org, verify_brand_access


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Engine 3: AI Visibility Evaluator"])


@router.post(
    "/brands/{brand_id}/visibility/scans",
    response_model=VisibilityScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start an AI Visibility scan for approved brand prompts"
)
async def create_visibility_scan(
    brand_id: str,
    payload: VisibilityScanCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiates an asynchronous AI Visibility scan.
    Enforces that caller is authorized to scan the requested brand.
    Queries the configured AI provider with approved Engine 2 prompts and evaluates
    brand mention presence, recommendation signals, competitors, and citations.
    """
    await verify_brand_access(brand_id, db, current_org)

    try:
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand_id,
            prompt_ids=payload.prompt_ids,
            provider=payload.provider,
            model_name=payload.model_name,
            max_prompts=payload.max_prompts or 20,
            force_rescan=payload.force_rescan,
            db=db
        )
        return VisibilityScanResponse.model_validate(scan)
    except ValueError as ve:
        err_msg = str(ve)
        if "Brand not found" in err_msg:
            raise HTTPException(status_code=404, detail="Brand not found.")
        if "no approved prompts" in err_msg:
            raise HTTPException(status_code=400, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
    except Exception as e:
        logger.exception(f"Error initiating visibility scan for brand {brand_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate AI visibility scan due to an internal error."
        )


@router.get(
    "/brands/{brand_id}/visibility/scans/{scan_id}",
    response_model=VisibilityScanResponse,
    summary="Get status and summary metrics for an AI visibility scan"
)
async def get_visibility_scan(
    brand_id: str,
    scan_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """Inspects live progress and aggregated metrics of an authorized visibility scan run."""
    await verify_brand_access(brand_id, db, current_org)

    try:
        scan = await VisibilityEvaluatorService.get_scan(scan_id, brand_id, db)
        return VisibilityScanResponse.model_validate(scan)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get(
    "/brands/{brand_id}/visibility/scans",
    response_model=VisibilityScanListResponse,
    summary="List historical visibility scans for brand comparison"
)
async def list_visibility_scans(
    brand_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all past visibility scan runs for an authorized brand."""
    await verify_brand_access(brand_id, db, current_org)

    try:
        scans = await VisibilityEvaluatorService.list_scans(brand_id, db)
        return VisibilityScanListResponse(
            items=[VisibilityScanResponse.model_validate(s) for s in scans],
            total=len(scans)
        )
    except ValueError as ve:
        if "Brand not found" in str(ve):
            raise HTTPException(status_code=404, detail="Brand not found.")
        raise HTTPException(status_code=400, detail=str(ve))


@router.get(
    "/brands/{brand_id}/visibility/scans/{scan_id}/results",
    response_model=VisibilityScanDetailResponse,
    summary="Get detailed prompt-level visibility evaluation results for a scan"
)
async def get_visibility_scan_results(
    brand_id: str,
    scan_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns full scan summary alongside verbatim AI responses,
    mention context snippets, competitor detections, and citations for each prompt.
    """
    await verify_brand_access(brand_id, db, current_org)

    try:
        scan, results = await VisibilityEvaluatorService.get_scan_results(scan_id, brand_id, db)
        return VisibilityScanDetailResponse(
            scan=VisibilityScanResponse.model_validate(scan),
            results=[VisibilityResultResponse.model_validate(r) for r in results]
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


@router.get(
    "/brands/{brand_id}/visibility/scans/{scan_id}/diagnosis",
    response_model=DiagnosisReport,
    summary="Get evidence-backed diagnosis and testable action recommendations for a scan"
)
async def get_visibility_scan_diagnosis(
    brand_id: str,
    scan_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Synthesizes empirical findings across Engine 1 facts, Engine 2 prompts,
    and Engine 3 evaluation results into structured, testable remediation actions.
    """
    await verify_brand_access(brand_id, db, current_org)

    try:
        report = await VisibilityDiagnosisService.diagnose_scan(scan_id, brand_id, db)
        return report
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))


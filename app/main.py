"""Main FastAPI application entry point for Auralyt MVP — Engine 1."""
from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.base import Base
from app.db.session import engine
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    setup_logging(debug=settings.DEBUG)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Keep existing SQLite deployments restart-safe until Alembic is run.
        # Each statement is isolated because older databases may have a subset.
        from sqlalchemy import text
        for statement in (
            "ALTER TABLE profile_runs ADD COLUMN profile_version INTEGER DEFAULT 1 NOT NULL",
            "ALTER TABLE brand_facts ADD COLUMN fact_key VARCHAR(512)",
            "ALTER TABLE brand_facts ADD COLUMN supporting_evidence JSON",
            "ALTER TABLE brand_facts ADD COLUMN is_rejected BOOLEAN DEFAULT 0 NOT NULL",
            "ALTER TABLE brand_facts ADD COLUMN is_superseded BOOLEAN DEFAULT 0 NOT NULL",
            "ALTER TABLE brand_facts ADD COLUMN is_stale BOOLEAN DEFAULT 0 NOT NULL",
            "ALTER TABLE brand_facts ADD COLUMN last_seen_at DATETIME",
            "ALTER TABLE brand_facts ADD COLUMN superseded_at DATETIME",
        ):
            try:
                await conn.execute(text(statement))
            except Exception:
                pass
    # Reconcile any orphaned/interrupted Engine 3 visibility scans
    from app.evaluator.service import VisibilityEvaluatorService
    await VisibilityEvaluatorService.reconcile_interrupted_scans()
    yield
    # Cleanup on shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Engine 1: Brand & Website Profiler for Auralyt AI visibility intelligence platform.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
app.include_router(api_router)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/dashboard", include_in_schema=False)
    async def serve_dashboard():
        return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "engine": "Engine 1: Brand & Website Profiler",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }

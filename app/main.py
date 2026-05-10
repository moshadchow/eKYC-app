from __future__ import annotations
import os
import sys
from contextlib import asynccontextmanager

# Allow direct execution of backend/app/main.py as a script.
if __name__ == "__main__" and __package__ is None:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)
    __package__ = "app"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin import router as admin_router
from app.api.v1.applications import router as applications_router
from app.api.v1.audit_lifecycle import audit_router, lifecycle_router
from app.api.v1.auth_agent import router as agent_auth_router
from app.api.v1.auth_customer import router as customer_auth_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.pre_check import router as pre_check_router
from app.api.v1.verification import router as verification_router
from app.api.v1.notifications import router as notifications_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.notification_dispatcher import start_dispatcher, stop_dispatcher
    start_dispatcher()
    yield
    stop_dispatcher()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="""
## eKYC Onboarding API

Bangladesh Capital Market & Insurance eKYC Platform
compliant with **BFIU e-KYC Guidelines** (Circular No. 29, March 2026).

### Key flows
- **Phase 1** — Customer & agent authentication with OTP and 2FA
- **Phase 2** — Pre-onboarding decision engine (Simplified vs Regular)
- **Phase 3** — Self check-in onboarding (face-match, liveness detection)
- **Phase 4** — Assisted onboarding (fingerprint + agent data entry)
- **Phase 5** — NID validation & biometric verification (mock EC API)
- **Phase 7** — AML compliance screening (UN sanctions, PEP/IP, adverse media)
- **Phase 8** — Risk grading engine with EDD trigger (score ≥ 15 = high)
- **Phase 9** — Maker-checker approval workflow with 4-eyes enforcement
- **Phase 11** — Immutable audit trail
- **Phase 12** — KYC lifecycle management and periodic refresh
        """,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": "Internal server error", "detail": str(exc)},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    PREFIX = "/api/v1"

    app.include_router(customer_auth_router, prefix=PREFIX)
    app.include_router(agent_auth_router, prefix=PREFIX)
    app.include_router(pre_check_router, prefix=PREFIX)
    app.include_router(applications_router, prefix=PREFIX)
    app.include_router(verification_router, prefix=PREFIX)
    app.include_router(compliance_router, prefix=PREFIX)
    app.include_router(admin_router, prefix=PREFIX)
    app.include_router(audit_router, prefix=PREFIX)
    app.include_router(lifecycle_router, prefix=PREFIX)
    app.include_router(notifications_router, prefix=PREFIX)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/api/docs",
            "status": "running",
        }

    @app.get("/health", tags=["System"])
    async def health():
        return {"status": "healthy", "version": settings.APP_VERSION}

    return app


app = create_app()

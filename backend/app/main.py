from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="Personal Advisor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "environment": settings.ENVIRONMENT}


from app.advisor.router import router as advisor_router
from app.audit import models as _audit_models  # noqa: F401 - register audit_events metadata
from app.documents.router import router as documents_router
from app.finance.router import router as finance_router
from app.identity.router import router as identity_router
from app.inbox.router import router as inbox_router
from app.security.csrf import require_csrf
from app.work.router import router as work_router

csrf_dependency = [Depends(require_csrf)]

app.include_router(
    identity_router, prefix="/api/auth", tags=["identity"], dependencies=csrf_dependency
)
app.include_router(
    finance_router, prefix="/api/finance", tags=["finance"], dependencies=csrf_dependency
)
app.include_router(work_router, prefix="/api/work", tags=["work"], dependencies=csrf_dependency)
app.include_router(inbox_router, prefix="/api/inbox", tags=["inbox"], dependencies=csrf_dependency)
app.include_router(
    advisor_router, prefix="/api/advisor", tags=["advisor"], dependencies=csrf_dependency
)
app.include_router(
    documents_router, prefix="/api/documents", tags=["documents"], dependencies=csrf_dependency
)

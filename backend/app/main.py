from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.db.database import engine, Base
from backend.app.db.models import *  # ensure all models register with Base.metadata

from backend.app.modules.auth.router import router as auth_router
from backend.app.modules.business.router import router as business_router
from backend.app.modules.account.router import router as account_router
from backend.app.modules.category.router import router as category_router
from backend.app.modules.transaction.router import router as transaction_router
from backend.app.modules.reconciliation.router import router as reconciliation_router
from backend.app.modules.analytics.router import router as analytics_router
from backend.app.modules.webhooks.router import router as webhooks_router
from backend.app.modules.audit.router import router as audit_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup (especially for local dev / SQLite testing)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root & Health Check Endpoints
@app.get("/")
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": "1.0.0",
        "docs": f"{settings.API_V1_STR}/docs",
        "status": "online",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


# Mount API V1 Routers
api_v1_prefix = settings.API_V1_STR

app.include_router(auth_router, prefix=api_v1_prefix)
app.include_router(business_router, prefix=api_v1_prefix)
app.include_router(account_router, prefix=api_v1_prefix)
app.include_router(category_router, prefix=api_v1_prefix)
app.include_router(transaction_router, prefix=api_v1_prefix)
app.include_router(reconciliation_router, prefix=api_v1_prefix)
app.include_router(analytics_router, prefix=api_v1_prefix)
app.include_router(webhooks_router, prefix=api_v1_prefix)
app.include_router(audit_router, prefix=api_v1_prefix)

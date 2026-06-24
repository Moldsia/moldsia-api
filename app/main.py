from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.pricing_routes import router as pricing_router
from app.api.public_quote_routes import router as public_quote_router
from app.api.routes import router as analysis_router
from app.core.logging_config import configure_logging
from app.core.settings import settings


configure_logging()

app = FastAPI(
    title=settings.app_name,
    description="MVP API para analisar geometrias STEP/IGES com CadQuery/OpenCascade.",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis_router, prefix="/api")
app.include_router(pricing_router, prefix="/api")
app.include_router(public_quote_router, prefix="/api")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "version": settings.app_version}

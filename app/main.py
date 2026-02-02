"""Main FastAPI application."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from pathlib import Path

from app.config import settings
from app.database import init_db
from app.scheduler import scheduler
from app.routers import (
    shopify,
    snkrdunk,
    price_plans,
    booster_variants,
    booster_inventory,
    mappings,
    reports,
    health,
    translations,
    competitors,
    suppliers,
    history,
)
from app.routers import settings as settings_router

# Initialize database tables on startup
init_db()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="FastAPI service for managing Shopify prices with SNKRDUNK integration"
)

# Setup static files and templates
app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["Health"])
app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["Settings"])
app.include_router(translations.router, prefix="/api/v1/translations", tags=["Translations"])
app.include_router(competitors.router, prefix="/api/v1/competitors", tags=["Competitors"])
app.include_router(suppliers.router, prefix="/api/v1", tags=["Suppliers"])
app.include_router(shopify.router, prefix="/api/v1/shopify", tags=["Shopify"])
app.include_router(snkrdunk.router, prefix="/api/v1/snkrdunk", tags=["SNKRDUNK"])
app.include_router(price_plans.router, prefix="/api/v1/price-plans", tags=["Price Plans"])
app.include_router(booster_variants.router, prefix="/api/v1/booster-variants", tags=["Booster Variants"])
app.include_router(booster_inventory.router, prefix="/api/v1/booster-inventory", tags=["Booster Inventory"])
app.include_router(mappings.router, prefix="/api/v1/mappings", tags=["Mappings"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(history.router, tags=["History"])


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Serve the web interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.api_route("/api")
async def api_root():
    """API information endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.on_event("startup")
async def startup_event():
    """Start background scheduler on app startup."""
    scheduler.start()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background scheduler on app shutdown."""
    scheduler.stop()


import os
from pathlib import Path

from dotenv import load_dotenv
from app.api.dashboard_routes import router as dashboard_router

# ---------------------------------------------------------------
# load_dotenv MUST run before any app imports.
#
# Modules like app.db.database call get_settings() at module level
# to create the SQLAlchemy engine.  If load_dotenv() hasn't run by
# that point, pydantic-settings never sees the .env values, and the
# lru_cache on get_settings() locks in stale defaults for the rest
# of the process.
# ---------------------------------------------------------------
load_dotenv(override=True)
print(f"CHAT MODEL: {os.environ.get('AI_CHAT_CHAT_MODEL', 'NOT SET')}")
print(f"MAX TOKENS: {os.environ.get('AI_CHAT_REPLY_MAX_TOKENS', 'NOT SET')}")

# Sanity check (remove once the key issue is confirmed fixed)
_key = os.environ.get("OPENROUTER_API_KEY", "")
print(f"ENV KEY LOADED (last 8): ...{_key[-8:]}" if _key else "WARNING: OPENROUTER_API_KEY not set!")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.ai_routes import router as ai_router
from app.core.config import get_settings
from app.db.database import Base, engine

import logging
from app.api.search_routes import router as search_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
logger.info(f"Settings loaded — API key ending: ...{settings.openrouter_api_key[-8:]}")
# logger.info(settings.MODEL_NAME)
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)
logger.info("APPLICATION STARTING")
app.include_router(dashboard_router)
app.include_router(search_router)

# -----------------------------
# CORS
# ----------------------------- 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Database startup
# -----------------------------
@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)


# -----------------------------
# Health check
# -----------------------------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "service": settings.app_name,
    }


# -----------------------------
# Chat UI
# -----------------------------
@app.get("/chat", tags=["Chat Ui"])
def chat_ui():
    logger.info("CHAT ENDPOINT HIT")
    """
    Serves the frontend chat UI.

    Expected file location:
    app/static/chat.html
    """

    chat_file = Path(__file__).resolve().parent / "static" / "chat.html"

    if not chat_file.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "chat.html not found",
                "expected_path": str(chat_file),
                "fix": "Create app/static/chat.html and place the updated UI file there.",
            },
        )

    return FileResponse(
        path=str(chat_file),
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# -----------------------------
# AI API routes
# -----------------------------
app.include_router(ai_router)
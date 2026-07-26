"""
Search endpoints — turn a generated ICP into an actual company list.

Place at: app/api/search_routes.py

Mount in main.py:
    from app.api.search_routes import router as search_router
    app.include_router(search_router)

Endpoints:
    POST /search/from-recipe        → search using a recipe you paste in
    POST /search/from-session/{id}  → search using a completed session's ICP
    GET  /search/backends           → list available backends and their status
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.services.icp_search import search_from_recipe, normalize_recipe
from app.db.database import get_db
from app.db.models import ICPProfile, OnboardingSession

router = APIRouter(prefix="/search", tags=["Search"])


class SearchFromRecipeRequest(BaseModel):
    search_recipe: dict = Field(..., description="A search_recipe object from an ICP")
    backend: str = Field("mock", description="'mock' or 'apollo'")
    limit: int = Field(10, ge=1, le=100)


class SearchFromSessionRequest(BaseModel):
    backend: str = Field("mock", description="'mock' or 'apollo'")
    limit: int = Field(10, ge=1, le=100)


def _resolve_api_key(backend: str) -> str:
    """
    Reads the provider key from the environment.
    Kept out of Settings deliberately so search stays an optional add-on —
    the core app runs fine with no search provider configured at all.
    """
    if backend == "apollo":
        key = os.environ.get("APOLLO_API_KEY", "")
        if not key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "APOLLO_API_KEY is not set. Add it to your .env file, "
                    "or use backend='mock' to try the flow without a provider."
                ),
            )
        return key
    return ""


@router.get("/backends")
def list_backends() -> dict:
    """Shows which backends exist and whether each is usable right now."""
    return {
        "backends": [
            {
                "name": "mock",
                "available": True,
                "requires_key": False,
                "description": (
                    "Synthetic results generated from the recipe filters. "
                    "No API key needed. Every row is tagged source='mock'."
                ),
            },
            {
                "name": "apollo",
                "available": bool(os.environ.get("APOLLO_API_KEY")),
                "requires_key": True,
                "env_var": "APOLLO_API_KEY",
                "description": (
                    "Live Apollo.io organization search. "
                    "Verify field names against docs.apollo.io before production use."
                ),
            },
        ]
    }


@router.post("/from-recipe")
def search_from_recipe_endpoint(request: SearchFromRecipeRequest) -> dict:
    """
    Runs a search from a recipe passed directly in the request body.
    Useful for testing a recipe without creating a session.
    """
    api_key = _resolve_api_key(request.backend)
    try:
        return search_from_recipe(
            search_recipe=request.search_recipe,
            backend=request.backend,
            api_key=api_key,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search backend failed: {exc}")


@router.post("/from-session/{session_id}")
def search_from_session(
    session_id: str,
    request: SearchFromSessionRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    The main path: takes a completed onboarding session, pulls its generated
    search_recipe, and runs the search. This is the step that was missing
    between "ICP generated" and "here are your target companies."
    """
    session = (
        db.query(OnboardingSession)
        .filter(OnboardingSession.id == session_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    icp = (
        db.query(ICPProfile)
        .filter(ICPProfile.session_id == session_id)
        .first()
    )
    if not icp:
        raise HTTPException(
            status_code=404,
            detail="No ICP has been generated for this session yet.",
        )
    if not icp.search_recipe:
        raise HTTPException(
            status_code=422,
            detail="This ICP has no search_recipe attached.",
        )

    api_key = _resolve_api_key(request.backend)
    try:
        result = search_from_recipe(
            search_recipe=icp.search_recipe,
            backend=request.backend,
            api_key=api_key,
            limit=request.limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Search backend failed: {exc}")

    # Attach ICP context so the caller knows which profile produced these results.
    result["icp_context"] = {
        "session_id": session_id,
        "icp_name": icp.icp_name,
        "mode": icp.mode,
        "generation_method": icp.generation_method,
        "needs_review": icp.needs_review,
    }
    return result


@router.post("/preview-filters")
def preview_filters(request: SearchFromRecipeRequest) -> dict:
    """
    Normalizes a recipe WITHOUT running a search.
    Use this to debug why a search returned nothing — it shows exactly which
    filters were extracted from the recipe and which came back empty.
    """
    filters = normalize_recipe(request.search_recipe)
    return {
        "filters": filters.__dict__,
        "is_empty": filters.is_empty(),
        "note": (
            "is_empty=true means no usable filters were found. "
            "Check whether the ICP fell back to a placeholder profile."
        ),
    }

"""
Observability dashboard — JSON API + static HTML UI.

Mount in main.py:
    from app.api.dashboard_routes import router as dashboard_router
    app.include_router(dashboard_router)

Endpoints:
    GET /dashboard              → serves dashboard.html from app/static/
    GET /dashboard/metrics      → JSON aggregate metrics
    GET /dashboard/events       → JSON filterable event list
    GET /dashboard/events/{id}  → JSON single event detail with session answers
"""
    
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import GenerationEvent, OnboardingSession, OnboardingAnswer

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _window_start(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _serialize_event(e: GenerationEvent) -> dict:
    return {
        "id": e.id,
        "session_id": e.session_id,
        "outcome": e.outcome,
        "fallback_reason": e.fallback_reason,
        "mode": e.mode,
        "model_used": e.model_used,
        "used_backup": e.used_backup,
        "latency_ms": e.latency_ms,
        "retry_count": e.retry_count,
        "prompt_tokens": e.prompt_tokens,
        "completion_tokens": e.completion_tokens,
        "total_tokens": e.total_tokens,
        "quality_score": e.quality_score,
        "answers_provided_count": e.answers_provided_count,
        "error_detail": e.error_detail,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ------------------------------------------------------------------
# HTML dashboard — serves the static file
# ------------------------------------------------------------------

@router.get("", tags=["Dashboard"])
def dashboard_view():
    html_path = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"
    if not html_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "dashboard.html not found",
                "expected_path": str(html_path),
                "fix": "Place dashboard.html in app/static/dashboard.html",
            },
        )
    return FileResponse(
        path=str(html_path),
        media_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


# ------------------------------------------------------------------
# JSON API — aggregate metrics
# ------------------------------------------------------------------

@router.get("/metrics")
def metrics(hours: int = 24, db: Session = Depends(get_db)) -> dict:
    since = _window_start(hours)
    base = db.query(GenerationEvent).filter(GenerationEvent.created_at >= since)
    total = base.count()

    outcome_rows = (
        db.query(GenerationEvent.outcome, func.count(GenerationEvent.id))
        .filter(GenerationEvent.created_at >= since)
        .group_by(GenerationEvent.outcome)
        .all()
    )
    outcomes = {o: c for o, c in outcome_rows}
    fallback_count = outcomes.get("fallback", 0)
    error_count = outcomes.get("error", 0)

    reason_rows = (
        db.query(GenerationEvent.fallback_reason, func.count(GenerationEvent.id))
        .filter(GenerationEvent.created_at >= since)
        .filter(GenerationEvent.fallback_reason.isnot(None))
        .group_by(GenerationEvent.fallback_reason)
        .all()
    )
    fallback_reasons = {r: c for r, c in reason_rows}

    model_rows = (
        db.query(
            GenerationEvent.model_used,
            GenerationEvent.outcome,
            func.count(GenerationEvent.id),
        )
        .filter(GenerationEvent.created_at >= since)
        .group_by(GenerationEvent.model_used, GenerationEvent.outcome)
        .all()
    )
    per_model: dict[str, dict] = {}
    for model, outcome, count in model_rows:
        m = per_model.setdefault(model or "unknown", {"total": 0, "fallback": 0})
        m["total"] += count
        if outcome == "fallback":
            m["fallback"] += count
    for m in per_model.values():
        m["fallback_rate"] = round(m["fallback"] / m["total"], 3) if m["total"] else 0.0

    latencies = sorted(
        v[0] for v in
        base.with_entities(GenerationEvent.latency_ms)
            .filter(GenerationEvent.latency_ms.isnot(None)).all()
    )

    def pct(p: float):
        if not latencies:
            return None
        idx = min(int(len(latencies) * p), len(latencies) - 1)
        return latencies[idx]

    mode_rows = (
        db.query(GenerationEvent.mode, func.count(GenerationEvent.id))
        .filter(GenerationEvent.created_at >= since)
        .group_by(GenerationEvent.mode)
        .all()
    )

    return {
        "window_hours": hours,
        "total_generations": total,
        "fallback_rate": round(fallback_count / total, 3) if total else 0.0,
        "error_rate": round(error_count / total, 3) if total else 0.0,
        "outcomes": outcomes,
        "fallback_reasons": fallback_reasons,
        "per_model": per_model,
        "by_mode": {m or "unknown": c for m, c in mode_rows},
        "latency_ms": {
            "p50": pct(0.50),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "samples": len(latencies),
        },
    }


# ------------------------------------------------------------------
# JSON API — event list with filtering
# ------------------------------------------------------------------

@router.get("/events")
def list_events(
    outcome: Optional[str] = Query(None),
    fallback_reason: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    model_used: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    min_latency: Optional[int] = Query(None),
    max_quality: Optional[int] = Query(None),
    hours: int = Query(24),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    since = _window_start(hours)
    q = (
        db.query(GenerationEvent)
        .filter(GenerationEvent.created_at >= since)
        .order_by(desc(GenerationEvent.created_at))
    )

    if outcome:
        q = q.filter(GenerationEvent.outcome == outcome)
    if fallback_reason:
        q = q.filter(GenerationEvent.fallback_reason == fallback_reason)
    if mode:
        q = q.filter(GenerationEvent.mode == mode)
    if model_used:
        q = q.filter(GenerationEvent.model_used.contains(model_used))
    if session_id:
        q = q.filter(GenerationEvent.session_id == session_id)
    if min_latency is not None:
        q = q.filter(GenerationEvent.latency_ms >= min_latency)
    if max_quality is not None:
        q = q.filter(GenerationEvent.quality_score <= max_quality)

    total = q.count()
    events = q.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
        "filters_applied": {
            k: v for k, v in {
                "outcome": outcome, "fallback_reason": fallback_reason,
                "mode": mode, "model_used": model_used,
                "session_id": session_id, "min_latency": min_latency,
                "max_quality": max_quality, "hours": hours,
            }.items() if v is not None
        },
        "events": [_serialize_event(e) for e in events],
    }


# ------------------------------------------------------------------
# JSON API — single event detail with session context
# ------------------------------------------------------------------

@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)) -> dict:
    event = db.query(GenerationEvent).filter(GenerationEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found.")

    result = _serialize_event(event)

    if event.session_id:
        session = (
            db.query(OnboardingSession)
            .filter(OnboardingSession.id == event.session_id)
            .first()
        )
        if session:
            result["session"] = {
                "status": session.status,
                "mode": session.mode,
                "current_step": session.current_step,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            }

        answers = (
            db.query(OnboardingAnswer)
            .filter(OnboardingAnswer.session_id == event.session_id)
            .order_by(OnboardingAnswer.id.asc())
            .all()
        )
        result["answers"] = {a.question_key: a.answer_text for a in answers}

    return result
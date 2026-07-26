from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.ai.schemas.onboarding import (
    ICPBuildRequest,
    ICPOutputData,
    OnboardingMessageRequest,
    OnboardingResponse,
    PlanRecommendationData,
    PlanRecommendationRequest,
    SessionSummaryResponse,
    StartOnboardingRequest,
)
from app.ai.services.icp_builder import ICPBuilder
from app.ai.services.onboarding_service import OnboardingService
from app.ai.services.plan_recommender import PlanRecommender
from app.db.database import get_db
from app.db.models import OnboardingSession

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/onboarding/start", response_model=OnboardingResponse)
def start_onboarding(
    request: StartOnboardingRequest,
    db: Session = Depends(get_db),
):
    service = OnboardingService(db)
    return service.start(request)


@router.post("/onboarding/message", response_model=OnboardingResponse)
def send_onboarding_message(
    request: OnboardingMessageRequest,
    db: Session = Depends(get_db),
):
    service = OnboardingService(db)
    return service.handle_message(
        session_id=request.session_id,
        message=request.message,
    )


@router.get("/onboarding/session/{session_id}", response_model=SessionSummaryResponse)
def get_onboarding_session(
    session_id: str,
    db: Session = Depends(get_db),
):
    service = OnboardingService(db)
    return service.get_summary(session_id)


@router.get("/onboarding/report/{session_id}")
def download_onboarding_report(
    session_id: str,
    db: Session = Depends(get_db),
):
    session = (
        db.query(OnboardingSession)
        .filter(OnboardingSession.id == session_id)
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Onboarding session not found.")

    if not session.report_path:
        raise HTTPException(status_code=404, detail="Report has not been generated yet.")

    report_path = Path(session.report_path)

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file is missing on server.")

    return FileResponse(
        path=str(report_path),
        filename=report_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.post("/icp/build", response_model=ICPOutputData)
def build_icp(request: ICPBuildRequest):
    builder = ICPBuilder()
    return builder.build_from_answers(
        mode=request.mode,
        answers=request.answers,
    )


@router.post("/plan/recommend", response_model=PlanRecommendationData)
def recommend_plan(request: PlanRecommendationRequest):
    recommender = PlanRecommender()
    return recommender.recommend(request)
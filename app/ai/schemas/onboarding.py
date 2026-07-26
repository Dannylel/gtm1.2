from typing import Any, Optional, Literal
from pydantic import BaseModel, Field


class StartOnboardingRequest(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    business_name: Optional[str] = None


class OnboardingMessageRequest(BaseModel):
    session_id: str
    message: str


class ICPBuildRequest(BaseModel):
    # "conversational" is accepted here but mapped to "advanced" internally before
    # hitting ICPBuilder, which only knows beginner / advanced.
    mode: Literal["beginner", "advanced", "conversational"]
    answers: dict[str, str]


class ICPOutputData(BaseModel):
    mode: Literal["beginner", "advanced"]
    icp_name: str
    icp_summary: str
    icp_data: dict[str, Any]
    search_recipe: dict[str, Any]
    icp_quality: dict[str, Any]
    generation_method: str = "gemini_structured_output"
    needs_review: bool = False


class OnboardingResponse(BaseModel):
    session_id: str
    status: str
    mode: Optional[str] = None
    current_step: int
    question: Optional[str] = None
    question_key: Optional[str] = None
    mode_instruction: Optional[str] = None
    icp_output: Optional[ICPOutputData] = None
    report_path: Optional[str] = None
    report_download_url: Optional[str] = None
    # Signals the frontend to render a constrained input control
    # (radio buttons, checkboxes, dropdown) instead of or alongside
    # the free-text input. None means free text only.
    # Shape: {type: radio|checkbox|dropdown, options: [{label, value}], allow_custom: bool}
    ui_hint: Optional[dict] = None


class SessionSummaryResponse(BaseModel):
    session_id: str
    status: str
    mode: Optional[str] = None
    current_step: int
    answers: dict[str, str]
    icp_output: Optional[ICPOutputData] = None
    report_path: Optional[str] = None
    report_download_url: Optional[str] = None


class PlanRecommendationData(BaseModel):
    recommended_plan: str
    confidence: int
    reasons: list[str]
    next_steps: list[str]


class PlanRecommendationRequest(BaseModel):
    team_size: int = Field(default=1)
    expected_monthly_company_searches: int = Field(default=0)
    expected_monthly_contacts: int = Field(default=0)
    expected_monthly_emails: int = Field(default=0)
    crm_required: bool = False
    salesforce_required: bool = False
    number_of_sending_domains: int = 1
    support_required: str = "standard"
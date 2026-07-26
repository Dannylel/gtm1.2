import json
import re
import traceback

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.config.icp_questions import (
    MODE_SELECTION_MESSAGE,
    ADVANCED_QUESTIONS,
    get_advanced_field_map,
    get_advanced_ui_hint,
    get_questions_for_mode,
)
from app.ai.schemas.onboarding import (
    ICPOutputData,
    OnboardingResponse,
    SessionSummaryResponse,
    StartOnboardingRequest,
)
from app.ai.services.icp_builder import ICPBuilder
from app.ai.services.report_generator import OnboardingReportGenerator
from app.db.models import (
    AIDatasetExample,
    ConversationTurn,
    GenerationEvent,
    ICPProfile,
    OnboardingAnswer,
    OnboardingSession,
    TokenUsageLog,
    User,
    utcnow,
)
from app.ai.monitoring.generation_events import (
    Outcome,
    FallbackReason,
    weighted_completeness,
)
import time as _time

import logging
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Module-level constants
# ------------------------------------------------------------------

_ICP_READY_RE = re.compile(r"<ICP_READY>(.*?)</ICP_READY>", re.DOTALL)
_FIELD_TAG_RE  = re.compile(r"<FIELD:\s*(\w+)\s*>", re.IGNORECASE)

# Advanced mode: backend enforces exactly this many questions, then shows
# the optional continuation menu. The LLM is told to plan accordingly.
ADVANCED_MAX_QUESTIONS = 5

# Conversational mode: safety backstop regardless of completion score.
MAX_TURNS = 20

# Words / phrases treated as "yes, generate" at the confirmation step.
_CONFIRM_WORDS = {
    "yes", "y", "yep", "yup", "yeah", "correct", "looks good", "good",
    "ok", "okay", "confirm", "proceed", "generate", "go", "sure",
    "that's right", "thats right", "looks right", "all good", "perfect",
}

# Detects user intent to generate immediately during conversational mode.
# Catches natural phrases without requiring exact phrasing.
_GENERATE_NOW_RE = re.compile(
    r"\b(generate|create|build)\s*(me\s+)?(the\s+|my\s+|an?\s+)?icp\b"
    r"|\b(generate|create|build)\s*(it|now|please)\b"
    r"|\bjust\s+(generate|go|proceed|do\s+it)\b"
    r"|\bgo\s+ahead\b"
    r"|\bskip\s+(to\s+)?(generation|the\s+icp|generating)\b"
    r"|\benough\s+(questions?|info(rmation)?)\b"
    r"|\bthat.?s\s+(enough|all|sufficient)\b",
    re.IGNORECASE,
)

# Optional fields offered in the advanced mode continuation menu.
# These are universally useful and don't assume what the LLM already covered.
_ADVANCED_OPTIONAL_FIELDS = [
    {"key": "revenue_or_budget",    "label": "Revenue range & budget"},
    {"key": "tools_and_technology", "label": "Tools & technology stack"},
    {"key": "buying_signals",       "label": "Buying signals & triggers"},
    {"key": "disqualifiers",        "label": "Companies to exclude"},
]

# ------------------------------------------------------------------
# Domain guard
# ------------------------------------------------------------------

_INJECTION_PATTERNS = re.compile(
    r"\b("
    r"jailbreak"
    r"|ignore\s+(all\s+)?previous\s+(instructions?|prompts?|context)"
    r"|you\s+are\s+now\s+(a\s+)?(different|new|unrestricted|dan)"
    r"|forget\s+(everything|all\s+previous)"
    r"|disregard\s+(all\s+)?previous"
    r"|act\s+as\s+((a|an|the)\s+)?(different|new|unrestricted|evil|dan)"
    r"|override\s+(your\s+)?(instructions?|system|prompt)"
    r"|porn|nude|naked|explicit\s+content"
    r")\b",
    re.IGNORECASE,
)

_INJECTION_REPLY = (
    "That's not something I can help with here. "
    "I'm focused on building your Ideal Customer Profile — "
    "let's continue from where we left off."
)


def _domain_guard(message: str) -> str | None:
    if _INJECTION_PATTERNS.search(message):
        return _INJECTION_REPLY
    return None


# ------------------------------------------------------------------
# UI hints — mode selection, beginner, and confirmation
# ------------------------------------------------------------------

_HINT_MODE_SELECTION = {
    "type": "radio",
    "allow_custom": False,
    "options": [
        {"label": "Quick mode (3 questions)",        "value": "1"},
        {"label": "Detailed mode (5 questions)",     "value": "2"},
        {"label": "Conversational mode (just chat)", "value": "3"},
    ],
}

_HINT_CONFIRMATION = {
    "type": "radio",
    "allow_custom": True,
    "options": [
        {"label": "Yes — generate my ICP",          "value": "yes"},
        {"label": "No — I want to make changes",    "value": "no, I want to make changes"},
    ],
}

_BEGINNER_UI_HINTS: dict[str, dict] = {
    "company_size": {
        "type": "radio",
        "allow_custom": True,
        "options": [
            {"label": "Micro   (1–10 employees)",    "value": "micro, 1-10 employees"},
            {"label": "Small   (11–50 employees)",   "value": "small, 11-50 employees"},
            {"label": "Mid     (51–300 employees)",  "value": "mid-sized, 51-300 employees"},
            {"label": "Large   (300–1,000)",         "value": "large, 300-1000 employees"},
            {"label": "Enterprise (1,000+)",         "value": "enterprise, 1000+ employees"},
        ],
    },
    "decision_maker": {
        "type": "checkbox",
        "allow_custom": True,
        "options": [
            {"label": "Owner / Founder",        "value": "owner or founder"},
            {"label": "CEO / COO",               "value": "CEO or COO"},
            {"label": "CTO / IT Head",           "value": "CTO or IT head"},
            {"label": "CFO / Finance Head",      "value": "CFO or finance head"},
            {"label": "Head of Sales / RevOps",  "value": "head of sales or RevOps"},
            {"label": "Head of Operations",      "value": "head of operations"},
            {"label": "Head of Marketing",       "value": "head of marketing"},
            {"label": "Procurement Manager",     "value": "procurement manager"},
        ],
    },
}

_OPENER_ADVANCED = (
    "Let's build a detailed ICP for your go-to-market strategy. "
    "I'll ask you 5 focused questions — at least 2 of which will have quick-select options "
    "so you can answer fast.\n\n"
    "To start: what does your company sell, and what specific problem does it solve?"
)

_OPENER_CONVERSATIONAL = (
    "Hey! Let's figure out who your ideal customers are.\n\n"
    "No forms, no fixed questions — just tell me about your business and we'll work it out. "
    "Keep it as casual as you like.\n\n"
    "What does your company do?"
)


class OnboardingService:
    def __init__(self, db: Session):
        self.db = db
        self.icp_builder = ICPBuilder()
        self.llm = self.icp_builder.llm

    # ------------------------------------------------------------------
    # Short topic labels for the system prompt
    # ------------------------------------------------------------------

    _ADVANCED_TOPIC_LABELS = {
        "business_context":     "what the company sells and the problem it solves",
        "industry_fit":         "best-fit industries, acceptable industries, industries to avoid",
        "target_geography":     "target countries, cities, or regions",
        "employee_range":       "ideal company headcount range",
        "revenue_or_budget":    "revenue range or typical customer budget",
        "company_stage":        "stage of target companies (growing, funded, scaling, etc.)",
        "pain_points":          "problems that make a company a good fit",
        "tools_and_technology": "tools or platforms they should already be using",
        "buying_signals":       "signs that a company needs them right now",
        "buyer_roles":          "who to contact first and who influences the decision",
        "disqualifiers":        "companies to avoid even if they match other filters",
        "usage_goal":           "expected monthly volume of searches, contacts, or outreach",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _get_question_ui_hint(self, question_key: str) -> dict | None:
        return _BEGINNER_UI_HINTS.get(question_key)

    def start(self, request: StartOnboardingRequest) -> OnboardingResponse:
        user = None
        if request.user_id:
            user = self.db.query(User).filter(User.id == request.user_id).first()
        if not user and (request.email or request.business_name):
            user = User(email=request.email, business_name=request.business_name)
            self.db.add(user)
            self.db.flush()

        session = OnboardingSession(
            user_id=user.id if user else None,
            status="mode_selection",
            mode=None,
            current_step=0,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return OnboardingResponse(
            session_id=session.id,
            status=session.status,
            mode=session.mode,
            current_step=session.current_step,
            question=MODE_SELECTION_MESSAGE,
            question_key="mode_selection",
            mode_instruction="Choose Quick mode, Detailed mode, or Conversational mode.",
            icp_output=None,
            report_path=None,
            report_download_url=None,
            ui_hint=_HINT_MODE_SELECTION,
        )

    def handle_message(self, session_id: str, message: str) -> OnboardingResponse:
        session = self._get_session(session_id)

        if session.status == "completed":
            return self._completed_response(session)

        if session.status == "mode_selection":
            return self._handle_mode_selection(session, message)

        if session.status == "pending_confirmation":
            return self._handle_confirmation(session, message)

        # Advanced mode optional continuation menu
        if session.status == "optional_continuation":
            return self._handle_optional_continuation(session, message)

        # Advanced mode optional field being answered
        if session.status.startswith("optional_answering:"):
            return self._handle_optional_answer(session, message)

        if not session.mode:
            raise HTTPException(status_code=400, detail="ICP mode is not selected.")

        if session.mode == "advanced":
            return self._handle_advanced_turn(session, message)

        if session.mode == "conversational":
            return self._handle_conversational_turn(session, message)

        return self._handle_beginner_turn(session, message)

    def get_summary(self, session_id: str) -> SessionSummaryResponse:
        session = self._get_session(session_id)
        answers = self._answers_dict(session)
        icp_output = None
        if session.icp_profile:
            icp_output = self._icp_model_to_schema(session.icp_profile)
        return SessionSummaryResponse(
            session_id=session.id,
            status=session.status,
            mode=session.mode,
            current_step=session.current_step,
            answers=answers,
            icp_output=icp_output,
            report_path=session.report_path,
            report_download_url=f"/ai/onboarding/report/{session.id}" if session.report_path else None,
        )

    # ------------------------------------------------------------------
    # Mode selection
    # ------------------------------------------------------------------

    def _handle_mode_selection(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        mode = self._detect_mode(message)
        session.mode = mode
        session.status = "in_progress"

        if mode in ("advanced", "conversational"):
            return self._start_conversational(session)

        # Beginner
        questions = get_questions_for_mode("beginner")
        if not self._is_explicit_beginner_choice(message):
            first_q = questions[0]
            self.db.add(OnboardingAnswer(
                session_id=session.id, mode=mode,
                question_key=first_q["key"], question_text=first_q["text"],
                answer_text=message,
            ))
            session.current_step = 1
            if session.current_step < len(questions):
                next_q = questions[session.current_step]
                self.db.commit()
                self.db.refresh(session)
                return OnboardingResponse(
                    session_id=session.id, status=session.status, mode=session.mode,
                    current_step=session.current_step, question=next_q["text"],
                    question_key=next_q["key"],
                    mode_instruction="Got it — 2 quick follow-up questions.",
                    icp_output=None, report_path=None, report_download_url=None,
                    ui_hint=self._get_question_ui_hint(next_q["key"]),
                )
            self.db.commit()
            self.db.refresh(session)
            return self._present_confirmation(session)

        session.current_step = 0
        self.db.commit()
        self.db.refresh(session)
        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=questions[0]["text"],
            question_key=questions[0]["key"],
            mode_instruction="You are now in Quick Mode.",
            icp_output=None, report_path=None, report_download_url=None,
            ui_hint=self._get_question_ui_hint(questions[0]["key"]),
        )

    def _detect_mode(self, message: str) -> str:
        c = message.strip().lower()
        if c in {"2", "option 2"} or re.fullmatch(r"option\s*2", c): return "advanced"
        if c in {"3", "option 3"} or re.fullmatch(r"option\s*3", c): return "conversational"
        if c in {"1", "option 1"} or re.fullmatch(r"option\s*1", c): return "beginner"
        if re.search(r"\bdetail", c) or re.search(r"\b(advanced|thorough|deep|comprehensive|structured)\b", c): return "advanced"
        if re.search(r"\bconvers", c) or re.search(r"\b(chat|talk|natural|casual|free|discuss)\b", c): return "conversational"
        if re.search(r"\b(quick|fast|simple|basic|beginner|easy|short|brief)\b", c): return "beginner"
        return "beginner"

    def _is_explicit_beginner_choice(self, message: str) -> bool:
        c = message.strip().lower()
        return (c in {"1", "option 1"} or bool(re.fullmatch(r"option\s*1", c))
                or bool(re.search(r"\b(quick|fast|simple|basic|beginner|easy|short|brief)\b", c)))

    # ------------------------------------------------------------------
    # Beginner mode — exactly 3 questions, then confirmation
    # ------------------------------------------------------------------

    def _handle_beginner_turn(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        questions = get_questions_for_mode("beginner")  # now always 3

        if session.current_step >= len(questions):
            return self._present_confirmation(session)

        question = questions[session.current_step]
        self.db.add(OnboardingAnswer(
            session_id=session.id, mode=session.mode,
            question_key=question["key"], question_text=question["text"],
            answer_text=message,
        ))
        session.current_step += 1

        if session.current_step < len(questions):
            next_q = questions[session.current_step]
            self.db.commit()
            self.db.refresh(session)
            return OnboardingResponse(
                session_id=session.id, status=session.status, mode=session.mode,
                current_step=session.current_step, question=next_q["text"],
                question_key=next_q["key"], mode_instruction=None,
                icp_output=None, report_path=None, report_download_url=None,
                ui_hint=self._get_question_ui_hint(next_q["key"]),
            )

        self.db.commit()
        self.db.refresh(session)
        return self._present_confirmation(session)

    # ------------------------------------------------------------------
    # Advanced mode — 5 LLM-driven questions, then optional continuation
    # ------------------------------------------------------------------

    def _start_conversational(self, session: OnboardingSession) -> OnboardingResponse:
        session.current_step = 0
        opener = _OPENER_ADVANCED if session.mode == "advanced" else _OPENER_CONVERSATIONAL
        mode_label = "Advanced" if session.mode == "advanced" else "Conversational"

        self._add_turn(session.id, "assistant", opener)
        self.db.commit()
        self.db.refresh(session)

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=opener,
            question_key="opening",
            mode_instruction=f"You are now in {mode_label} Mode.",
            icp_output=None, report_path=None, report_download_url=None,
        )

    def _handle_advanced_turn(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        """
        Drives 5 LLM questions for advanced mode.
        The LLM picks which fields to ask about (always starts with business_context).
        Backend enforces the 5-question cap and routes to the optional continuation menu.
        """
        blocked = _domain_guard(message)
        if blocked:
            return OnboardingResponse(
                session_id=session.id, status=session.status, mode=session.mode,
                current_step=session.current_step, question=blocked,
                question_key="domain_guard", mode_instruction=None,
                icp_output=None, report_path=None, report_download_url=None,
            )

        self._add_turn(session.id, "user", message)
        session.current_step += 1

        # After ADVANCED_MAX_QUESTIONS turns, show the optional continuation menu.
        if session.current_step >= ADVANCED_MAX_QUESTIONS:
            self.db.commit()
            self.db.refresh(session)
            return self._present_optional_continuation(session)

        # Call LLM for next question.
        messages = self._build_llm_messages(session.id)
        try:
            result = self.llm.chat(
                messages=messages,
                system_prompt=self._build_system_prompt("advanced"),
            )
            self._log_tokens(session.id, "chat", result)
            reply = result.text
        except Exception as exc:
            logger.error(f"advanced chat() failed: {exc}\n{traceback.format_exc()}")
            reply = "Sorry, technical issue. Could you say that again?"

        field_key = self._extract_field_tag(reply)
        ui_hint   = get_advanced_ui_hint(field_key) if field_key else None

        display_reply = _ICP_READY_RE.sub("", reply)
        display_reply = _FIELD_TAG_RE.sub("", display_reply).strip()
        if not display_reply:
            display_reply = "Got it! Let me ask you one more thing."

        self._add_turn(session.id, "assistant", display_reply)
        self.db.commit()
        self.db.refresh(session)

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=display_reply,
            question_key=field_key or "advanced", mode_instruction=None,
            icp_output=None, report_path=None, report_download_url=None,
            ui_hint=ui_hint,
        )

    def _present_optional_continuation(self, session: OnboardingSession) -> OnboardingResponse:
        """
        Shown after 5 advanced-mode questions. The user can deepen any of the
        4 universally useful optional fields, or generate the ICP immediately.
        """
        session.status = "optional_continuation"
        self.db.commit()
        self.db.refresh(session)

        message = (
            "I have a solid foundation for your ICP.\n\n"
            "You can generate it now, or go deeper on one more area first:"
        )

        ui_hint = {
            "type": "radio",
            "allow_custom": False,
            "options": [
                {"label": opt["label"],          "value": f"continue:{opt['key']}"}
                for opt in _ADVANCED_OPTIONAL_FIELDS
            ] + [
                {"label": "Generate ICP now →",  "value": "generate_now"},
            ],
        }

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=message,
            question_key="optional_continuation", mode_instruction=None,
            icp_output=None, report_path=None, report_download_url=None,
            ui_hint=ui_hint,
        )

    def _handle_optional_continuation(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        """Handles the user's choice at the optional continuation menu."""
        stripped = message.strip()

        if stripped == "generate_now" or stripped.lower() in _CONFIRM_WORDS:
            self._force_extract_from_transcript(session)
            return self._present_confirmation(session)

        if stripped.startswith("continue:"):
            field_key = stripped.replace("continue:", "").strip()
            field_q = next((q for q in ADVANCED_QUESTIONS if q["key"] == field_key), None)
            if not field_q:
                self._force_extract_from_transcript(session)
                return self._present_confirmation(session)

            self._add_turn(session.id, "user", message)
            session.status = f"optional_answering:{field_key}"
            self.db.commit()
            self.db.refresh(session)

            return OnboardingResponse(
                session_id=session.id, status=session.status, mode=session.mode,
                current_step=session.current_step, question=field_q["text"],
                question_key=field_key, mode_instruction=None,
                icp_output=None, report_path=None, report_download_url=None,
                ui_hint=get_advanced_ui_hint(field_key),
            )

        # Unrecognised input → just generate.
        self._force_extract_from_transcript(session)
        return self._present_confirmation(session)

    def _handle_optional_answer(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        """Stores the user's answer to an optional field, then presents confirmation."""
        field_key = session.status.replace("optional_answering:", "").strip()
        field_q   = next((q for q in ADVANCED_QUESTIONS if q["key"] == field_key), None)
        q_text    = field_q["text"] if field_q else field_key

        # First extract everything from the transcript (covers the 5 main questions).
        self._force_extract_from_transcript(session)

        # Then upsert the optional field directly — direct answer beats extraction.
        existing = (
            self.db.query(OnboardingAnswer)
            .filter(
                OnboardingAnswer.session_id == session.id,
                OnboardingAnswer.question_key == field_key,
            )
            .first()
        )
        if existing:
            existing.answer_text = message.strip()
        else:
            self.db.add(OnboardingAnswer(
                session_id=session.id, mode=session.mode,
                question_key=field_key, question_text=q_text,
                answer_text=message.strip(),
            ))

        self._add_turn(session.id, "user", message)
        self.db.flush()
        self.db.commit()
        self.db.refresh(session)

        return self._present_confirmation(session)

    # ------------------------------------------------------------------
    # Conversational mode — adaptive, priority + variance, completion score
    # ------------------------------------------------------------------

    def _handle_conversational_turn(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        blocked = _domain_guard(message)
        if blocked:
            return OnboardingResponse(
                session_id=session.id, status=session.status, mode=session.mode,
                current_step=session.current_step, question=blocked,
                question_key="domain_guard", mode_instruction=None,
                icp_output=None, report_path=None, report_download_url=None,
            )

        # Detect explicit "generate now" intent — respect it immediately.
        if _GENERATE_NOW_RE.search(message):
            self._add_turn(session.id, "user", message)
            self.db.flush()
            answers = self._answers_dict(session)
            if len(answers) < 3:
                self._force_extract_from_transcript(session)
            self.db.commit()
            self.db.refresh(session)
            return self._present_confirmation(
                session,
                closing_line="Sure — generating your ICP now based on what we've covered.",
            )

        self._add_turn(session.id, "user", message)
        session.current_step += 1

        messages = self._build_llm_messages(session.id)
        try:
            result = self.llm.chat(
                messages=messages,
                system_prompt=self._build_system_prompt("conversational"),
            )
            self._log_tokens(session.id, "chat", result)
            reply = result.text
        except Exception as exc:
            logger.error(f"chat() failed: {exc}\n{traceback.format_exc()}")
            reply = "Sorry, I ran into a technical issue. Could you repeat that?"

        fields = self._extract_icp_ready(reply)
        field_key = self._extract_field_tag(reply)
        ui_hint   = get_advanced_ui_hint(field_key) if field_key else None

        display_reply = _ICP_READY_RE.sub("", reply)
        display_reply = _FIELD_TAG_RE.sub("", display_reply).strip()
        if not display_reply:
            display_reply = "I have everything I need."

        if fields is not None:
            self._store_icp_ready_answers(session, fields)
            self._add_turn(session.id, "assistant", display_reply)
            self.db.flush()
            return self._present_confirmation(session, closing_line=display_reply)

        if session.current_step >= MAX_TURNS:
            self._add_turn(session.id, "assistant", display_reply)
            self.db.flush()
            return self._present_confirmation(
                session,
                closing_line=(
                    "We've covered a lot of ground. I've reached the maximum conversation "
                    "length, so I'm presenting what we have — you can still edit or add "
                    "anything at this step."
                ),
            )

        self._add_turn(session.id, "assistant", display_reply)
        self.db.commit()
        self.db.refresh(session)

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=display_reply,
            question_key=field_key or "conversational", mode_instruction=None,
            icp_output=None, report_path=None, report_download_url=None,
            ui_hint=ui_hint,
        )

    # ------------------------------------------------------------------
    # Completion score — conversational mode display metric
    # ------------------------------------------------------------------

    def _compute_completion_score(self, answers: dict[str, str]) -> dict:
        """
        Computes a coverage score for the conversational mode confirmation step.
        This is a DISPLAY metric shown to the user — it does NOT trigger generation.
        Generation is triggered by the LLM emitting <ICP_READY>, the user saying
        "generate now", or the turn cap being hit.

        Tiers:
        - Perfect  (90-100): all 5 priority+variance fields answered with detail
        - High     (70-89):  all 3 priority fields + at least 1 variance answered
        - Average  (50-69):  all 3 priority fields answered
        - Low      (30-49):  1-2 priority fields answered
        - Lowest   (0-29):   barely anything answered
        """
        priority_keys  = ["business_context", "industry_fit", "target_geography"]
        variance_keys  = ["pain_points", "buyer_roles"]
        other_keys     = ["employee_range", "revenue_or_budget", "company_stage",
                          "tools_and_technology", "buying_signals", "disqualifiers", "usage_goal"]

        def filled(key: str) -> bool:
            return bool(answers.get(key, "").strip())

        def has_detail(key: str) -> bool:
            return len(answers.get(key, "").strip()) >= 20

        priority_filled  = sum(1 for k in priority_keys if filled(k))
        variance_filled  = sum(1 for k in variance_keys if filled(k))
        other_filled     = sum(1 for k in other_keys if filled(k))

        # Points: priority=10 each, variance=7 each, other=3 each → max 79
        raw = priority_filled * 10 + variance_filled * 7 + other_filled * 3
        # Detail bonus: +2 per priority/variance field with ≥20 chars → max +10
        detail_bonus = sum(2 for k in (priority_keys + variance_keys) if has_detail(k))
        raw = min(79 + 10, raw + detail_bonus)

        score = min(100, int((raw / 89) * 100))

        if score >= 90:
            label = "Perfect coverage"
        elif score >= 70:
            label = "High coverage"
        elif score >= 50:
            label = "Average coverage"
        elif score >= 30:
            label = "Low coverage"
        else:
            label = "Minimal coverage"

        return {
            "score": score,
            "label": label,
            "priority_filled":  priority_filled,
            "priority_total":   len(priority_keys),
            "variance_filled":  variance_filled,
            "variance_total":   len(variance_keys),
        }

    # ------------------------------------------------------------------
    # Verification step — shown before generation for all modes
    # ------------------------------------------------------------------

    def _present_confirmation(
        self,
        session: OnboardingSession,
        closing_line: str = "",
    ) -> OnboardingResponse:
        session.status = "pending_confirmation"
        self.db.commit()
        self.db.refresh(session)

        answers = self._answers_dict(session)

        if session.mode in ("advanced", "conversational") and len(answers) < 4:
            logger.info("Answers sparse before confirmation — running force extraction.")
            self._force_extract_from_transcript(session)
            answers = self._answers_dict(session)

        summary = self._format_icp_summary(session.mode, answers)
        prefix  = f"{closing_line}\n\n" if closing_line else ""

        # For conversational mode, show the completion score.
        if session.mode == "conversational":
            score_data = self._compute_completion_score(answers)
            score_line = (
                f"\n📊 Coverage: {score_data['score']}% — {score_data['label']} "
                f"({score_data['priority_filled']}/{score_data['priority_total']} priority topics, "
                f"{score_data['variance_filled']}/{score_data['variance_total']} variance topics)\n"
            )
        else:
            score_line = ""

        message = (
            f"{prefix}"
            f"Here's what I've gathered. Please review before I generate your ICP:\n"
            f"{score_line}\n"
            f"{summary}\n\n"
            f"Reply **yes** to generate your ICP, or tell me what to change."
        )

        if session.mode in ("advanced", "conversational"):
            self._add_turn(session.id, "assistant", message)

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=message,
            question_key="pending_confirmation", mode_instruction=None,
            icp_output=None, report_path=None, report_download_url=None,
            ui_hint=_HINT_CONFIRMATION,
        )

    def _handle_confirmation(self, session: OnboardingSession, message: str) -> OnboardingResponse:
        cleaned = " ".join(message.strip().lower().split())

        if cleaned in _CONFIRM_WORDS:
            return self._finalize(session)

        if session.mode == "beginner":
            session.status = "in_progress"
            session.current_step = 0
            self.db.query(OnboardingAnswer).filter(
                OnboardingAnswer.session_id == session.id
            ).delete()
            self.db.commit()
            self.db.refresh(session)
            questions = get_questions_for_mode("beginner")
            return OnboardingResponse(
                session_id=session.id, status=session.status, mode=session.mode,
                current_step=session.current_step, question=questions[0]["text"],
                question_key=questions[0]["key"],
                mode_instruction="No problem — let's go through the questions again.",
                icp_output=None, report_path=None, report_download_url=None,
                ui_hint=self._get_question_ui_hint(questions[0]["key"]),
            )

        # Advanced / Conversational: feed correction back to the LLM.
        session.status = "in_progress"
        session.current_step = 0
        self.db.commit()

        if session.mode == "advanced":
            return self._handle_advanced_turn(session, message)
        return self._handle_conversational_turn(session, message)

    def _format_icp_summary(self, mode: str, answers: dict[str, str]) -> str:
        if mode == "beginner":
            labels = {
                "plain_target_description": "Target companies",
                "company_size":             "Company size",
                "decision_maker":           "Decision maker",
            }
        else:
            labels = {
                "business_context":     "What you sell",
                "industry_fit":         "Target industries",
                "target_geography":     "Geography",
                "employee_range":       "Company size",
                "revenue_or_budget":    "Revenue / budget",
                "company_stage":        "Company stage",
                "pain_points":          "Pain points",
                "tools_and_technology": "Tech stack",
                "buying_signals":       "Buying signals",
                "buyer_roles":          "Buyer roles",
                "disqualifiers":        "Disqualifiers",
                "usage_goal":           "Monthly usage goal",
            }
        return "\n".join(
            f"• {label}: {answers.get(key, '—')}"
            for key, label in labels.items()
        )

    # ------------------------------------------------------------------
    # System prompts
    # ------------------------------------------------------------------

    def _extract_field_tag(self, text: str) -> str | None:
        match = _FIELD_TAG_RE.search(text)
        if not match:
            return None
        key   = match.group(1).strip().lower()
        known = {q["key"] for q in ADVANCED_QUESTIONS}
        return key if key in known else None

    def _build_system_prompt(self, mode: str) -> str:
        field_map       = get_advanced_field_map()
        icp_ready_json  = json.dumps(
            {key: f"<fill: {key.replace('_', ' ')}>" for key in field_map},
            indent=2,
        )
        field_options   = "\n".join(
            f"  - {key}: {self._ADVANCED_TOPIC_LABELS.get(key, key)}"
            for key in field_map
        )

        icp_ready_instruction = f"""
FIELD TAGGING (required): After every turn where you are directly asking about a specific
ICP field, append on the LAST line of your reply:
  <FIELD: field_key>
using the exact key name. Do NOT tag acknowledgements, clarifications, or the ICP_READY turn.
The tag is stripped before the user sees it — it only drives the UI.

When finished, append immediately after your closing sentence:
<ICP_READY>
{icp_ready_json}
</ICP_READY>
Rules:
- Fill EVERY key. Infer sensible defaults for anything not mentioned.
- Normalize values: "medium companies" → "51-300 employees".
- Emit exactly ONCE.
- If the user requests a change after ICP_READY, emit a new complete ICP_READY block."""

        if mode == "advanced":
            return f"""You are a senior GTM strategist. Your task: ask EXACTLY 5 focused questions
to gather the information needed for a B2B Ideal Customer Profile. No more, no less.
After the 5th question is answered, the system takes over — do NOT try to generate the ICP yourself.

QUESTION 1 (mandatory — always first):
Ask what the company sells and the specific problem it solves.
Tag: <FIELD: business_context>

QUESTIONS 2–5 (your choice — pick the 4 most relevant for this specific business):
Available topics:
{field_options}

Selection guidance — adapt after reading their first answer:
- B2B software / SaaS        → prioritise: buyer_roles, pain_points, industry_fit, employee_range
- Enterprise / large accounts → prioritise: disqualifiers, revenue_or_budget, buyer_roles, tools_and_technology
- SMB / growth focus          → prioritise: pain_points, target_geography, company_stage, buying_signals
- Regulated industry           → prioritise: industry_fit, pain_points (compliance angle), buyer_roles, revenue_or_budget
- If the first answer or anything later answers another field by accident, count it as covered → do NOT re-ask, cover other topics instead

MANDATORY: At least 2 of your 5 questions must be about topics with predefined answer options
(industry_fit, target_geography, employee_range, revenue_or_budget, company_stage,
tools_and_technology, buying_signals, buyer_roles, usage_goal).
The system renders buttons/dropdowns for these automatically when you tag them correctly.

Style:
- One brief acknowledgement, then ONE question. Never ask multiple at once.
- Professional, direct, no filler.
- If an answer is vague, ask for the specific number or example in the same turn.

{icp_ready_instruction}"""

        else:  # conversational
            return f"""You are a friendly GTM consultant helping someone think through who their ideal
customers are. Casual, warm, exploratory tone. Vague answers are fine — normalize them yourself.

PRIORITY TOPICS — cover these first (combine naturally if it flows):
  1. business_context   — what they sell and the problem it solves
  2. industry + geography — target industries and regions (can ask together)
  3. company size + stage — headcount range and growth stage (can ask together)

VARIANCE TOPICS — cover after priority topics, both if relevant to this business:
  4. pain_points  — specific problems that make a company a good fit
  5. buyer_roles  — who to contact first, who influences the decision

BRANCH TOPICS — ask at most 1–2, only if priority/variance answers are thin or a specific
need is revealed by the conversation:
  revenue_or_budget, tools_and_technology, buying_signals, disqualifiers, usage_goal

Rules:
- ONE question per turn. Acknowledge first, then ask.
- Never reveal you're following a topic list or checklist.
- If the user goes off-topic, gently steer back in one sentence.
- If they don't know something, suggest a reasonable default and confirm it.
- If a topic was answered incidentally while discussing something else, count it as covered.
- If the user asks to generate immediately ("just generate", "go ahead", etc.),
  emit <ICP_READY> with whatever you have, inferring sensible defaults for uncovered topics.

COMPLETION: Emit <ICP_READY> when you have substantive answers across all 5 priority+variance
topics, OR when the information is rich enough for a meaningful ICP even if some topics are
partially covered. Depth matters more than breadth — a rich answer to 4 topics is better than
thin answers to 8.

{icp_ready_instruction}"""

    # ------------------------------------------------------------------
    # Transcript helpers
    # ------------------------------------------------------------------

    def _add_turn(self, session_id: str, role: str, content: str) -> None:
        self.db.add(ConversationTurn(
            session_id=session_id, role=role, content=content or ""
        ))
        self.db.flush()

    def _load_transcript(self, session_id: str) -> list[dict[str, str]]:
        turns = (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.session_id == session_id)
            .order_by(ConversationTurn.id.asc())
            .all()
        )
        return [{"role": t.role, "content": t.content} for t in turns]

    def _build_llm_messages(self, session_id: str) -> list[dict[str, str]]:
        turns = (
            self.db.query(ConversationTurn)
            .filter(ConversationTurn.session_id == session_id)
            .order_by(ConversationTurn.id.asc())
            .all()
        )
        messages = []
        seen_user = False
        for t in turns:
            if t.role == "user":
                seen_user = True
            if not seen_user:
                continue
            content = t.content
            if t.role == "assistant":
                content = _ICP_READY_RE.sub("", content).strip()
                if not content:
                    continue
            messages.append({"role": t.role, "content": content})
        return messages

    def _extract_icp_ready(self, text: str) -> dict | None:
        match = _ICP_READY_RE.search(text)
        if not match:
            return None
        raw = match.group(1).strip()
        try:
            result = json.loads(raw)
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.warning(f"ICP_READY strict parse failed ({e}). Attempting lenient parse. Raw:\n{raw[:500]}")
        try:
            cleaned = re.sub(r"^```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
            cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
            result  = json.loads(cleaned)
            if isinstance(result, dict):
                logger.info("ICP_READY recovered via lenient parse.")
                return result
        except Exception as e:
            logger.error(f"ICP_READY lenient parse also failed ({e}). Full raw:\n{raw}")
        return None

    def _force_extract_from_transcript(self, session: OnboardingSession) -> None:
        transcript = self._load_transcript(session.id)
        if not transcript:
            logger.warning("Force extract called but transcript is empty.")
            return

        field_map = get_advanced_field_map()
        recent    = transcript[-30:]
        transcript_text = "\n".join(
            f"{t['role'].upper()}: {t['content'][:400]}" for t in recent
        )

        prompt = (
            "Below is a sales/GTM conversation. Extract whatever was discussed about "
            "the user's ideal target market into the following fields. For anything not "
            "explicitly mentioned, infer a sensible default from the overall context. "
            "Never leave a field empty or null.\n\n"
            f"Required fields:\n"
            f"{json.dumps({k: self._ADVANCED_TOPIC_LABELS.get(k, k) for k in field_map}, indent=2)}\n\n"
            f"Conversation:\n{transcript_text}\n\n"
            "Return ONLY a flat JSON object with exactly these keys, all string values."
        )
        try:
            result = self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="You are a precise JSON extraction assistant. Return only valid JSON.",
            )
            self._log_tokens(session.id, "force_extract", result)
            text    = result.text.strip()
            text    = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
            text    = re.sub(r"```$", "", text).strip()
            text    = re.sub(r",\s*([}\]])", r"\1", text)
            fields  = json.loads(text)
            if isinstance(fields, dict):
                self._store_icp_ready_answers(session, fields)
                logger.info(f"Force extraction: {len([v for v in fields.values() if v])} fields.")
        except Exception as exc:
            logger.error(f"Force extraction failed: {exc}\n{traceback.format_exc()}")

    def _store_icp_ready_answers(self, session: OnboardingSession, fields: dict) -> None:
        field_map = get_advanced_field_map()
        for key, value in fields.items():
            if key not in field_map:
                continue
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(value).strip()
            if not value:
                continue
            existing = (
                self.db.query(OnboardingAnswer)
                .filter(
                    OnboardingAnswer.session_id == session.id,
                    OnboardingAnswer.question_key == key,
                )
                .first()
            )
            if existing:
                existing.answer_text = value
            else:
                self.db.add(OnboardingAnswer(
                    session_id=session.id, mode=session.mode,
                    question_key=key,
                    question_text=field_map[key],
                    answer_text=value,
                ))
        self.db.flush()

    # ------------------------------------------------------------------
    # Token logging
    # ------------------------------------------------------------------

    def _log_tokens(self, session_id: str, call_type: str, result) -> None:
        try:
            self.db.add(TokenUsageLog(
                session_id=session_id,
                call_type=call_type,
                model=self.llm.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                latency_ms=result.latency_ms,
            ))
            self.db.flush()
            session_total = (
                self.db.query(TokenUsageLog)
                .filter(TokenUsageLog.session_id == session_id)
                .all()
            )
            cumulative = sum(r.total_tokens for r in session_total)
            logger.info(
                f"TOKEN USAGE | session={session_id[:8]} call={call_type} "
                f"prompt={result.prompt_tokens} completion={result.completion_tokens} "
                f"total={result.total_tokens} latency={result.latency_ms}ms "
                f"session_cumulative={cumulative}"
            )
        except Exception as exc:
            logger.warning(f"Token logging failed (non-fatal): {exc}")

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def _categorize_failure(self, exc: Exception) -> str:
        """Maps an exception from the generation call to a fallback_reason category."""
        text = str(exc).lower()
        if "timeout" in text or "timed out" in text:
            return FallbackReason.TIMEOUT
        if "429" in text or "rate limit" in text or "quota" in text:
            return FallbackReason.RATE_LIMIT
        if "validation" in text or "schema" in text or "pydantic" in text:
            return FallbackReason.SCHEMA_INVALID
        if "402" in text or "credit" in text or "api" in text or "connection" in text or "openrouter" in text:
            return FallbackReason.PROVIDER_ERROR
        return FallbackReason.UNKNOWN

    def _record_generation_event(
        self,
        session: OnboardingSession,
        outcome: str,
        latency_ms: int,
        answers: dict,
        fallback_reason: str | None = None,
        quality_score: int | None = None,
        error_detail: str | None = None,
        used_backup: bool = False,
    ) -> None:
        """
        Writes one GenerationEvent row. Never raises — observability must not
        break the user-facing flow.
        """
        try:
            self.db.add(GenerationEvent(
                session_id=session.id,
                outcome=outcome,
                fallback_reason=fallback_reason,
                mode=session.mode,
                model_used=self.llm.model,
                used_backup="true" if used_backup else "false",
                latency_ms=latency_ms,
                retry_count=0,  # wire to provider retry count once exposed
                quality_score=quality_score,
                answers_provided_count=sum(1 for v in answers.values() if (v or "").strip()),
                error_detail=error_detail[:2000] if error_detail else None,
            ))
            self.db.flush()
            logger.info(
                f"GEN EVENT | session={session.id[:8]} outcome={outcome} "
                f"reason={fallback_reason} mode={session.mode} latency={latency_ms}ms"
            )
        except Exception as exc:
            logger.warning(f"GenerationEvent write failed (non-fatal): {exc}")

    def _finalize(self, session: OnboardingSession) -> OnboardingResponse:
        if session.status == "completed":
            return self._completed_response(session)

        answers      = self._answers_dict(session)
        builder_mode = "advanced" if session.mode in ("advanced", "conversational") else session.mode

        gemini_error = None
        fallback_reason = None
        _t0 = _time.monotonic()

        # Insufficient-info pre-check: if the weighted completeness is too low,
        # a successful LLM call could still only produce a thin profile. We skip
        # straight to the fallback and categorize it as insufficient_info — this
        # is a USER-domain outcome, not a system failure, and notably does NOT
        # implicate the model (so backup-model switching should ignore it).
        completeness = weighted_completeness(answers, builder_mode)
        if completeness < 0.25:
            logger.info(f"Insufficient info (weighted completeness={completeness:.2f}) — skipping LLM, using fallback.")
            icp_output        = self.icp_builder.fallback_profile(mode=builder_mode, answers=answers)
            generation_method = "fallback_profile"
            needs_review      = True
            fallback_reason   = FallbackReason.INSUFFICIENT_INFO
            if isinstance(icp_output.icp_quality, dict):
                icp_output.icp_quality["fallback_reason"] = fallback_reason
        else:
            try:
                icp_output        = self.icp_builder.build_from_answers(mode=builder_mode, answers=answers)
                generation_method = "gemini_structured_output"
                needs_review      = icp_output.needs_review
            except Exception as exc:
                gemini_error    = str(exc)
                fallback_reason = self._categorize_failure(exc)
                logger.error(f"ICP generation error [{fallback_reason}]:\n{traceback.format_exc()}")
                icp_output        = self.icp_builder.fallback_profile(mode=builder_mode, answers=answers)
                generation_method = "fallback_profile"
                needs_review      = True
                if isinstance(icp_output.icp_quality, dict):
                    icp_output.icp_quality["gemini_error"]    = gemini_error[:1000]
                    icp_output.icp_quality["fallback_reason"] = fallback_reason

        _latency_ms = int((_time.monotonic() - _t0) * 1000)

        # Pull the quality score for the event row, if present.
        _q_score = None
        if isinstance(icp_output.icp_quality, dict):
            raw_score = icp_output.icp_quality.get("score")
            if isinstance(raw_score, (int, float)):
                _q_score = int(raw_score)

        # Record the generation event (success or categorized fallback).
        self._record_generation_event(
            session=session,
            outcome=Outcome.SUCCESS if generation_method == "gemini_structured_output" else Outcome.FALLBACK,
            latency_ms=_latency_ms,
            answers=answers,
            fallback_reason=fallback_reason,
            quality_score=_q_score,
            error_detail=gemini_error,
            used_backup=False,  # wire to ModelHealth once backup switching exists
        )

        icp = ICPProfile(
            session_id=session.id, mode=builder_mode,
            icp_name=icp_output.icp_name, icp_summary=icp_output.icp_summary,
            icp_data=icp_output.icp_data, search_recipe=icp_output.search_recipe,
            icp_quality=icp_output.icp_quality, generation_method=generation_method,
            needs_review=str(needs_review).lower(),
        )
        dataset_example = AIDatasetExample(
            session_id=session.id,
            task_type=f"{session.mode}_icp_and_search_recipe_generation",
            input_json={"mode": session.mode, "answers": answers},
            output_json=icp_output.model_dump(),
            tags={
                "session_id": session.id, "source": "gtm_ai_icp_chatbot",
                "mode": session.mode, "builder_mode": builder_mode,
                "generation_method": generation_method,
                "can_be_used_for_finetuning": not needs_review,
                "can_be_used_for_evaluation": True,
                "gemini_error": gemini_error[:1000] if gemini_error else None,
            },
            feedback_label="pending_review",
        )

        session.status = "completed"
        self.db.add(icp)
        self.db.add(dataset_example)
        self.db.flush()

        report_generator  = OnboardingReportGenerator(self.db)
        report_path       = report_generator.generate(session.id)
        session.report_path          = report_path
        session.report_generated_at  = utcnow()
        self.db.commit()
        self.db.refresh(session)

        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=None, question_key=None,
            mode_instruction=None, icp_output=icp_output,
            report_path=session.report_path,
            report_download_url=f"/ai/onboarding/report/{session.id}",
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_session(self, session_id: str) -> OnboardingSession:
        session = (
            self.db.query(OnboardingSession)
            .filter(OnboardingSession.id == session_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Onboarding session not found.")
        return session

    def _answers_dict(self, session: OnboardingSession) -> dict[str, str]:
        answers = (
            self.db.query(OnboardingAnswer)
            .filter(OnboardingAnswer.session_id == session.id)
            .order_by(OnboardingAnswer.id.asc())
            .all()
        )
        return {a.question_key: a.answer_text for a in answers}

    def _completed_response(self, session: OnboardingSession) -> OnboardingResponse:
        return OnboardingResponse(
            session_id=session.id, status=session.status, mode=session.mode,
            current_step=session.current_step, question=None, question_key=None,
            mode_instruction=None,
            icp_output=self._icp_model_to_schema(session.icp_profile) if session.icp_profile else None,
            report_path=session.report_path,
            report_download_url=f"/ai/onboarding/report/{session.id}" if session.report_path else None,
        )

    def _icp_model_to_schema(self, icp: ICPProfile) -> ICPOutputData:
        return ICPOutputData(
            mode=icp.mode,
            icp_name=icp.icp_name or "",
            icp_summary=icp.icp_summary or "",
            icp_data=icp.icp_data or {},
            search_recipe=icp.search_recipe or {},
            icp_quality=icp.icp_quality or {},
            generation_method=icp.generation_method or "unknown",
            needs_review=True if icp.needs_review == "true" else False,
        )
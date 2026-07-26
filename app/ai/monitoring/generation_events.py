"""
Categorization constants and helpers for generation observability.

Keeping the reason strings here (not as inline literals) means:
- the dashboard and the writer agree on the exact vocabulary
- adding a new category is a one-line change in one place
- typos become impossible to introduce silently

Place this at app/ai/observability/generation_events.py (or wherever your
app package keeps small shared modules) and import from it.
"""


class Outcome:
    SUCCESS = "success"
    FALLBACK = "fallback"
    ERROR = "error"


class FallbackReason:
    INSUFFICIENT_INFO = "insufficient_info"   # user domain — thin answers, not a bug
    PROVIDER_ERROR = "provider_error"         # dependency domain — API threw
    TIMEOUT = "timeout"                       # dependency domain — call timed out
    RATE_LIMIT = "rate_limit"                 # dependency domain — 429 / quota
    SCHEMA_INVALID = "schema_invalid"         # LLM responded but failed validation
    BOTH_MODELS_DOWN = "both_models_down"     # primary + backup both failed
    UNKNOWN = "unknown"                        # uncategorized — investigate


# Per-field weights for the "insufficient_info" decision.
# Some fields matter far more to a usable ICP than others. A profile missing
# business_context is far weaker than one missing usage_goal. The weighted
# completeness score reflects that so we don't treat all gaps equally.
#
# Weights are relative, not absolute — only their ratios matter.
FIELD_WEIGHTS = {
    "business_context":     10,   # what they sell — without this there is no ICP
    "industry_fit":          9,
    "target_geography":      7,
    "buyer_roles":           7,
    "pain_points":           6,
    "employee_range":        5,
    "company_stage":         4,
    "buying_signals":        4,
    "revenue_or_budget":     3,
    "tools_and_technology":  3,
    "disqualifiers":         2,
    "usage_goal":            1,   # operational detail — barely affects ICP quality
}

# Beginner uses a different, smaller field set.
BEGINNER_FIELD_WEIGHTS = {
    "business_context":      10,
    "company_size":           6,
    "decision_maker":         6,
}


def weighted_completeness(answers: dict[str, str], mode: str) -> float:
    """
    Returns a 0.0-1.0 score of how complete the answers are, weighted so that
    important fields count more. Used to decide whether a generation should be
    treated as 'insufficient_info' rather than attempting (and likely wasting)
    an LLM call that can only produce a thin profile.

    A field counts as 'provided' only if it has real content (>= 3 chars after
    stripping), so empty strings and single punctuation don't inflate the score.
    """
    weights = BEGINNER_FIELD_WEIGHTS if mode == "beginner" else FIELD_WEIGHTS
    if not weights:
        return 0.0

    total_weight = sum(weights.values())
    earned = 0
    for key, weight in weights.items():
        value = (answers.get(key) or "").strip()
        if len(value) >= 3:
            earned += weight

    return earned / total_weight if total_weight else 0.0

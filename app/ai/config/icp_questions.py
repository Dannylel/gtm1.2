MODE_SELECTION_MESSAGE = """
Welcome to GTM AI ICP Builder.

How would you like to build your target profile?

1. Quick mode — 3 questions, fast results.
2. Detailed mode — 5 focused questions, richer ICP.
3. Conversational mode — just chat naturally, I'll guide the rest.

You can also directly type what kind of companies you want to find, and I'll start in Quick mode.
"""

# ------------------------------------------------------------------
# Beginner mode — exactly 3 questions.
# Q1: free text (what they're looking for)
# Q2: radio (company size — constrained, fast to answer)
# Q3: checkbox (decision maker roles — multi-select, no typing needed)
# ------------------------------------------------------------------

BEGINNER_QUESTIONS = [
    {
        "key": "business_context",
        "text": "What does your company sell, and what business problem does it solve?",
        "ui_hint": None,  # open-ended 
    },
    # {
    #     "key": "plain_target_description",
    #     "text": "In plain words, what kind of companies are you trying to reach?",
    #     "ui_hint": None,  # free text — open-ended by design
    # },
    {
        "key": "company_size",
        "text": "What size companies are you targeting?",
        "ui_hint": {
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
    },
    {
        "key": "decision_maker",
        "text": "Who usually makes the purchase decision at these companies?",
        "ui_hint": {
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
    },
]

# ------------------------------------------------------------------
# Advanced mode — 12 available fields, LLM picks the 5 most relevant.
# Each entry carries a ui_hint so the backend can render the right
# control when the LLM tags a question with <FIELD: key>.
# ------------------------------------------------------------------

ADVANCED_QUESTIONS = [
    {
        "key": "business_context",
        "text": "What does your company sell, and what business problem does it solve?",
        "ui_hint": None,  # open-ended — always the first question in advanced mode
    },
    {
        "key": "industry_fit",
        "text": "Which industries are your best fit, which are acceptable, and which should be avoided?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "SaaS / Software",                    "value": "SaaS / Software"},
                {"label": "Fintech / Banking",                  "value": "Fintech / Banking"},
                {"label": "Healthcare / MedTech",               "value": "Healthcare / MedTech"},
                {"label": "E-commerce / Retail",                "value": "E-commerce / Retail"},
                {"label": "Logistics / Supply Chain",           "value": "Logistics / Supply Chain"},
                {"label": "Manufacturing",                      "value": "Manufacturing"},
                {"label": "Legal / Compliance",                 "value": "Legal / Compliance"},
                {"label": "Consulting / Professional Services", "value": "Consulting / Professional Services"},
                {"label": "Real Estate / PropTech",             "value": "Real Estate / PropTech"},
                {"label": "Education / EdTech",                 "value": "Education / EdTech"},
                {"label": "Energy / Utilities",                 "value": "Energy / Utilities"},
                {"label": "Government / Public Sector",         "value": "Government / Public Sector"},
            ],
        },
    },
    {
        "key": "target_geography",
        "text": "Which countries, cities, or regions should GTM target first?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "United States",         "value": "United States"},
                {"label": "United Kingdom",        "value": "United Kingdom"},
                {"label": "Canada",                "value": "Canada"},
                {"label": "Australia",             "value": "Australia"},
                {"label": "Germany",               "value": "Germany"},
                {"label": "France",                "value": "France"},
                {"label": "Middle East (GCC)",     "value": "Middle East (GCC)"},
                {"label": "Southeast Asia",        "value": "Southeast Asia"},
                {"label": "Global / Remote-first", "value": "Global / Remote-first"},
            ],
        },
    },
    {
        "key": "employee_range",
        "text": "What employee range is ideal for your target companies?",
        "ui_hint": {
            "type": "radio",
            "allow_custom": True,
            "options": [
                {"label": "Micro (1–10)",       "value": "1-10 employees"},
                {"label": "Small (11–50)",       "value": "11-50 employees"},
                {"label": "Mid-market (51–300)", "value": "51-300 employees"},
                {"label": "Growth (301–1,000)",  "value": "301-1000 employees"},
                {"label": "Enterprise (1,000+)", "value": "1000+ employees"},
            ],
        },
    },
    {
        "key": "revenue_or_budget",
        "text": "What revenue range or customer budget level usually makes a company a good fit?",
        "ui_hint": {
            "type": "radio",
            "allow_custom": True,
            "options": [
                {"label": "Under $1M ARR",       "value": "under $1M ARR"},
                {"label": "$1M – $10M ARR",      "value": "$1M-$10M ARR"},
                {"label": "$10M – $50M ARR",     "value": "$10M-$50M ARR"},
                {"label": "$50M – $200M ARR",    "value": "$50M-$200M ARR"},
                {"label": "$200M+ / Enterprise", "value": "$200M+ or enterprise"},
            ],
        },
    },
    {
        "key": "company_stage",
        "text": "What stage should these companies be in?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "Pre-seed / Idea stage", "value": "pre-seed"},
                {"label": "Seed-funded",            "value": "seed-funded"},
                {"label": "Series A / B",           "value": "Series A/B"},
                {"label": "Growth / Scaling",       "value": "growing / scaling"},
                {"label": "Late stage / Pre-IPO",   "value": "late stage / pre-IPO"},
                {"label": "Public / Enterprise",    "value": "public / enterprise"},
                {"label": "Restructuring / Pivot",  "value": "restructuring or pivoting"},
            ],
        },
    },
    # {
    #     "key": "pain_points",
    #     "text": "What problems should these companies be experiencing for your offer to be relevant?",
    #     "ui_hint": None,  # context-specific, free text
    # },
    
    {
        "key": "buying_signals",
        "text": "What signs would show that a company may need you right now?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "Recent funding round",           "value": "recent funding round"},
                {"label": "Active hiring in target dept",   "value": "active hiring in target department"},
                {"label": "New C-suite / leadership hire",  "value": "new C-suite or leadership hire"},
                {"label": "Regulatory change in sector",    "value": "regulatory change in their sector"},
                {"label": "Recent M&A activity",            "value": "recent merger or acquisition"},
                {"label": "Technology migration / upgrade", "value": "technology migration or upgrade"},
                {"label": "Rapid headcount growth",         "value": "rapid headcount growth"},
                {"label": "Expansion into new market",      "value": "expansion into new market"},
            ],
        },
    },
    {
        "key": "buyer_roles",
        "text": "Who should GTM contact first, and who else may influence the decision?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "CEO / Founder",            "value": "CEO or Founder"},
                {"label": "CTO / VP Engineering",     "value": "CTO or VP Engineering"},
                {"label": "COO / VP Operations",      "value": "COO or VP Operations"},
                {"label": "CFO / VP Finance",         "value": "CFO or VP Finance"},
                {"label": "CMO / VP Marketing",       "value": "CMO or VP Marketing"},
                {"label": "VP Sales / RevOps",        "value": "VP Sales or RevOps"},
                {"label": "Head of IT / IT Director", "value": "Head of IT or IT Director"},
                {"label": "Product Manager / CPO",    "value": "Product Manager or CPO"},
                {"label": "Procurement Manager",      "value": "Procurement Manager"},
            ],
        },
    },
    {
        "key": "disqualifiers",
        "text": "What type of companies should GTM avoid even if they match the basic filters?",
        "ui_hint": None,  # context-specific, free text
    },
    {
        "key": "usage_goal",
        "text": "How many companies, contacts, or outreach messages do you expect to work with each month?",
        "ui_hint": {
            "type": "radio",
            "allow_custom": True,
            "options": [
                {"label": "Small  (< 500/mo)",        "value": "under 500 companies per month"},
                {"label": "Medium  (500–2,000/mo)",    "value": "500-2000 companies per month"},
                {"label": "Large  (2,000–10,000/mo)", "value": "2000-10000 companies per month"},
                {"label": "Very large  (10,000+/mo)", "value": "10000+ companies per month"},
            ],
        },
    },
    {
        "key": "tools_and_technology",
        "text": "Are there any tools, systems, or platforms they should already be using?",
        "ui_hint": {
            "type": "checkbox",
            "allow_custom": True,
            "options": [
                {"label": "Salesforce",             "value": "Salesforce"},
                {"label": "HubSpot",                "value": "HubSpot"},
                {"label": "SAP / Oracle ERP",       "value": "SAP or Oracle ERP"},
                {"label": "Microsoft 365",           "value": "Microsoft 365"},
                {"label": "Google Workspace",       "value": "Google Workspace"},
                {"label": "Slack",                  "value": "Slack"},
                {"label": "Jira / Confluence",      "value": "Jira / Confluence"},
                {"label": "AWS / Azure / GCP",      "value": "AWS / Azure / GCP"},
                {"label": "Shopify / WooCommerce",  "value": "Shopify or WooCommerce"},
                {"label": "Zendesk / Intercom",     "value": "Zendesk or Intercom"},
            ],
        },
    },
]

# Field keys the conversational mode must cover (same as advanced).
CONVERSATIONAL_FIELD_KEYS = [q["key"] for q in ADVANCED_QUESTIONS]


def get_questions_for_mode(mode: str) -> list[dict]:
    if mode == "beginner":
        return BEGINNER_QUESTIONS
    if mode == "advanced":
        return ADVANCED_QUESTIONS
    raise ValueError(f"Unsupported ICP mode: {mode}")


def get_advanced_field_map() -> dict[str, str]:
    """Returns {field_key: question_text} for all 12 advanced fields."""
    return {q["key"]: q["text"] for q in ADVANCED_QUESTIONS}


def get_advanced_ui_hint(field_key: str) -> dict | None:
    """
    Returns the ui_hint for a given advanced field key, or None for free-text fields.
    Called by the service when the LLM signals which field it is asking about
    via <FIELD: key>, and when serving predefined optional continuation questions.
    """
    for q in ADVANCED_QUESTIONS:
        if q["key"] == field_key:
            return q.get("ui_hint")
    return None
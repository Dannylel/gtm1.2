from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.schemas.onboarding import ICPOutputData


class ICPBuilder:
    def __init__(self):
        self.llm = GeminiProvider()

    def build_from_answers(self, mode: str, answers: dict[str, str]) -> ICPOutputData:
        if mode == "beginner":
            prompt = self._beginner_prompt(answers)
        elif mode == "advanced":
            prompt = self._advanced_prompt(answers)
        else:
            raise ValueError(f"Unsupported ICP mode: {mode}")

        return self.llm.generate_structured(prompt=prompt, schema=ICPOutputData)

    # ------------------------------------------------------------------
    # Prompts (unchanged)
    # ------------------------------------------------------------------

    def _beginner_prompt(self, answers: dict[str, str]) -> str:
        return f"""
You are GTM AI ICP Builder.

The user is in BEGINNER / QUICK MODE.

Your job:
Convert the user's simple answers into a useful beginner ICP and ready search recipe.

Do not just copy the user's sentences.
Normalize the answers into clean backend-ready fields.

The output must be valid JSON with exactly these top-level fields:

- mode
- icp_name
- icp_summary
- icp_data
- search_recipe
- icp_quality
- generation_method
- needs_review

The value of mode must be "beginner".
The value of generation_method must be "gemini_structured_output".
The value of needs_review should be false if output is usable.

Beginner ICP should include:
- target_company_type
- main_industry
- basic_sub_industries
- target_location
- company_size
- problem_or_need
- suggested_buyer_roles
- basic_exclusions
- minimum_viable_lead_record

Ready search recipe should include:
- include_industries
- exclude_industries
- locations
- employee_range
- keywords
- buyer_roles
- plain_english_search_summary

ICP quality should include:
- score
- strengths
- weaknesses
- missing_fields
- recommended_improvements

Rules:
- Use plain English.
- Avoid jargon.
- Do not invent specific company names.
- Extract clean values from the user's answers.
- If the user says B2B SaaS, map industry to Software / SaaS.
- If the user says New York, map location to New York, United States.
- If the user says mid-sized 50 to 300 employees, map employee range clearly.
- If the user mentions manual paperwork, slow approvals, repetitive workflows, map them as pain points and keywords.
- Suggested buyer roles should be clean role names, not full sentences.
- Basic exclusions should be sensible and relevant.
- Score the ICP quality on a scale of 0-100 using this rubric:

  Completeness (40 pts max): What fraction of the key beginner fields were provided?
    Key fields: target company type, industry, location, company size, buyer role, problem/need.
    Full coverage = 40. Partial scales proportionally.

  Specificity (30 pts max): Are values precise?
    Named industries, specific size ranges, named job titles = high.
    Vague terms like "big companies" or "IT people" without context = low.

  Actionability (30 pts max): Can the search_recipe fields filter a real company database?
    Named industries in standard taxonomies, parseable geography (country/city), 
    recognisable role titles = high. Abstract descriptions = low.

  Adjust ±5 for exceptional internal consistency or notable contradictions.
  Do not anchor to a fixed range — evaluate each ICP independently on the rubric.
- Mark missing fields only if actually missing.
- The output must be JSON only.

User answers:
{answers}

Return JSON in this structure:  

{{
  "mode": "beginner",
  "icp_name": "Short ICP name",
  "icp_summary": "Plain English ICP summary",
  "icp_data": {{
    "target_company_type": "",
    "main_industry": "",
    "basic_sub_industries": [],
    "target_location": [],
    "company_size": "",
    "problem_or_need": [],
    "suggested_buyer_roles": [],
    "basic_exclusions": [],
    "minimum_viable_lead_record": [
      "company_name",
      "website",
      "industry",
      "location",
      "estimated_employee_count",
      "matching_reason",
      "suggested_buyer_role",
      "confidence_score"
    ]
  }},
  "search_recipe": {{
    "include_industries": [],
    "exclude_industries": [],
    "locations": [],
    "employee_range": "",
    "keywords": [],
    "buyer_roles": [],
    "plain_english_search_summary": ""
  }},
  "icp_quality": {{
    "score": 0,
    "strengths": [],
    "weaknesses": [],
    "missing_fields": [],
    "recommended_improvements": []
  }},
  "generation_method": "gemini_structured_output",
  "needs_review": false
}}
"""

    def _advanced_prompt(self, answers: dict[str, str]) -> str:
        return f"""
You are GTM AI ICP Builder.

The user is in ADVANCED / DETAILED MODE.

Your job:
Convert detailed targeting answers into:
1. a fully enriched ICP profile
2. a ready search recipe for the GTM backend
3. ICP scoring logic
4. priority target segments
5. ICP quality review

Do not just copy the user's sentences.
Normalize the answers into clean backend-ready fields.

The output must be valid JSON with exactly these top-level fields:

- mode
- icp_name
- icp_summary
- icp_data
- search_recipe
- icp_quality
- generation_method
- needs_review

The value of mode must be "advanced".
The value of generation_method must be "gemini_structured_output".
The value of needs_review should be false if output is usable.

Advanced ICP should include:
- business_context
- best_fit_industries
- acceptable_industries
- excluded_industries
- target_geography
- employee_range
- revenue_range
- company_stage
- business_model
- technology_profile
- pain_and_use_case_fit
- buying_signals
- buyer_committee
- disqualifiers
- priority_segments
- lead_scoring_rules
- product_usage_context

Ready search recipe should include:
- include_filters
- exclude_filters
- priority_filters
- buyer_title_filters
- keyword_filters
- buying_signal_filters
- plain_english_search_summary

ICP quality should include:
- score
- strengths
- weaknesses
- missing_fields
- recommended_improvements

Rules:
- Separate ICP targeting from plan recommendation.
- The usage goal can be stored in product_usage_context but must not change the ICP itself.
- Do not recommend a pricing plan.
- Do not invent specific company names.
- Extract clean values from answers.
- Buyer roles should be clean role names.
- Buying signals should be usable by search/scoring later.
- Priority segments should be practical campaign segments.
- Lead scoring rules should describe how to score fit.
- Score the ICP quality on a scale of 0-100 using this rubric:

  Completeness (40 pts max): What fraction of the 12 ICP fields were provided with
    substantive answers? Required fields include: target industries, geography, company
    size, pain points, buyer roles, buying signals. Scale 0-40 proportionally.

  Specificity (30 pts max): Are values precise and machine-parseable?
    Named tools, exact employee ranges ("51-300"), named job titles, specific geographies = high.
    Vague terms ("medium companies", "decision makers") without context = low.

  Actionability (30 pts max): Can the search_recipe fields directly filter a company database?
    Industries in standard taxonomies, parseable geography at country/city level,
    role titles matching LinkedIn/Apollo filters, named tools = high. Abstract = low.

  You may apply domain knowledge to adjust ±5 if fields are internally consistent and
  logically coherent, or if notable contradictions exist (e.g. "enterprise companies"
  with "under $1M ARR"). Do NOT anchor to a fixed range — evaluate each ICP independently.
- The output must be JSON only.

User answers:
{answers}

Return JSON in this structure:

{{
  "mode": "advanced",
  "icp_name": "Short ICP name",
  "icp_summary": "Plain English ICP summary",
  "icp_data": {{
    "business_context": {{
      "user_company_description": "",
      "product_or_service": "",
      "primary_value_proposition": "",
      "main_use_cases": []
    }},
    "best_fit_industries": [],
    "acceptable_industries": [],
    "excluded_industries": [],
    "target_geography": {{
      "primary": [],
      "secondary": []
    }},
    "employee_range": {{
      "ideal": "",
      "acceptable": "",
      "excluded": ""
    }},
    "revenue_range": "",
    "company_stage": [],
    "business_model": [],
    "technology_profile": {{
      "tools_they_may_use": [],
      "tools_that_increase_fit": [],
      "technology_maturity": ""
    }},
    "pain_and_use_case_fit": {{
      "primary_pain_points": [],
      "business_impact": [],
      "best_entry_angle": ""
    }},
    "buying_signals": [],
    "buyer_committee": {{
      "economic_buyer": [],
      "technical_buyer": [],
      "champion": [],
      "possible_blockers": [],
      "recommended_first_contacts": []
    }},
    "disqualifiers": [],
    "priority_segments": [],
    "lead_scoring_rules": {{
      "industry_fit": "",
      "geography_fit": "",
      "company_size_fit": "",
      "revenue_fit": "",
      "technology_fit": "",
      "pain_fit": "",
      "buying_signal_fit": "",
      "buyer_role_fit": "",
      "disqualifier_check": ""
    }},
    "product_usage_context": ""
  }},
  "search_recipe": {{
    "include_filters": {{
      "industries": [],
      "locations": [],
      "employee_range": "",
      "revenue_range": "",
      "company_stage": [],
      "technologies": []
    }},
    "exclude_filters": {{
      "industries": [],
      "company_sizes": [],
      "conditions": []
    }},
    "priority_filters": [],
    "buyer_title_filters": [],
    "keyword_filters": [],
    "buying_signal_filters": [],
    "plain_english_search_summary": ""
  }},
  "icp_quality": {{
    "score": 0,
    "strengths": [],
    "weaknesses": [],
    "missing_fields": [],
    "recommended_improvements": []
  }},
  "generation_method": "gemini_structured_output",
  "needs_review": false
}}
"""

    # ------------------------------------------------------------------
    # Fallback profile — answers-first, no hardcoded domain content
    #
    # Called only when build_from_answers() throws (API crash, token
    # error, Pydantic validation failure). No LLM calls here — pure
    # Python so it cannot fail the same way the main path did.
    #
    # Rule: every field must come from answers or a truly generic
    # placeholder ("Not specified"). Never hardcode industry, geography,
    # company size, or any other domain-specific content.
    # ------------------------------------------------------------------

    def fallback_profile(self, mode: str, answers: dict[str, str]) -> ICPOutputData:

        if mode == "beginner":
            plain_target   = answers.get("plain_target_description", "").strip()
            target_location = answers.get("target_location", "").strip()
            company_size    = answers.get("company_size", "").strip()
            problem_or_need = answers.get("problem_or_need", "").strip()
            decision_maker  = answers.get("decision_maker", "").strip()

            inferred_industries = self._infer_industries(plain_target)
            inferred_roles      = self._infer_roles(decision_maker or plain_target)
            inferred_keywords   = self._infer_keywords(problem_or_need + " " + plain_target)

            icp_name    = self._derive_name(plain_target, inferred_industries)
            icp_summary = self._derive_summary_beginner(
                plain_target, target_location, company_size, problem_or_need
            )

            icp_data = {
                "target_company_type": plain_target or "Not specified",
                "main_industry": (
                    inferred_industries[0] if inferred_industries else "Not specified"
                ),
                "basic_sub_industries": inferred_industries or ["Not specified"],
                "target_location": (
                    self._split_or_wrap(target_location) if target_location
                    else ["Not specified"]
                ),
                "company_size": self._normalize_size(company_size) or "Not specified",
                "problem_or_need": (
                    self._split_or_wrap(problem_or_need) if problem_or_need
                    else inferred_keywords[:3] or ["Not specified"]
                ),
                "suggested_buyer_roles": inferred_roles or ["Not specified"],
                "basic_exclusions": [
                    "Companies that do not match the described target",
                    "Companies with no visible need for the described solution",
                ],
                "minimum_viable_lead_record": [
                    "company_name",
                    "website",
                    "industry",
                    "location",
                    "estimated_employee_count",
                    "matching_reason",
                    "suggested_buyer_role",
                    "confidence_score",
                ],
            }

            search_recipe = {
                "include_industries": inferred_industries or ["Not specified"],
                "exclude_industries": [],
                "locations": (
                    self._split_or_wrap(target_location) if target_location
                    else ["Not specified"]
                ),
                "employee_range": self._normalize_size(company_size) or "Not specified",
                "keywords": inferred_keywords or ["Not specified"],
                "buyer_roles": inferred_roles or ["Not specified"],
                "plain_english_search_summary": self._derive_search_summary(
                    plain_target, target_location, company_size,
                    problem_or_need, inferred_roles
                ),
            }

            filled = sum(
                1 for v in [plain_target, target_location, company_size,
                             problem_or_need, decision_maker]
                if v
            )
            score = max(30, int((filled / 5) * 70))

            icp_quality = {
                "score": score,
                "strengths": [
                    f"'{k}' was provided"
                    for k, v in {
                        "target description": plain_target,
                        "location": target_location,
                        "company size": company_size,
                        "problem / need": problem_or_need,
                        "decision maker": decision_maker,
                    }.items()
                    if v
                ],
                "weaknesses": [
                    "Generate d using fallback profile — primary LLM generation failed.",
                    "Output reflects user answers directly without AI enrichment.",
                ],
                "missing_fields": [
                    k for k, v in {
                        "target description": plain_target,
                        "location": target_location,
                        "company size": company_size,
                        "problem / need": problem_or_need,
                        "decision maker": decision_maker,
                    }.items()
                    if not v
                ],
                "recommended_improvements": [
                    "Retry ICP generation to get the full AI-enriched output.",
                    "Ensure all five beginner questions are answered before retrying.",
                ],
            }

        else:
            # Advanced / Conversational
            business_context    = answers.get("business_context", "").strip()
            industry_fit        = answers.get("industry_fit", "").strip()
            target_geography    = answers.get("target_geography", "").strip()
            employee_range      = answers.get("employee_range", "").strip()
            revenue_or_budget   = answers.get("revenue_or_budget", "").strip()
            company_stage       = answers.get("company_stage", "").strip()
            pain_points         = answers.get("pain_points", "").strip()
            tools_and_technology = answers.get("tools_and_technology", "").strip()
            buying_signals      = answers.get("buying_signals", "").strip()
            buyer_roles         = answers.get("buyer_roles", "").strip()
            disqualifiers       = answers.get("disqualifiers", "").strip()
            usage_goal          = answers.get("usage_goal", "").strip()

            inferred_industries = self._infer_industries(
                industry_fit + " " + business_context
            )
            inferred_roles = self._infer_roles(buyer_roles or business_context)
            inferred_keywords = self._infer_keywords(
                pain_points + " " + buying_signals + " " + business_context
            )

            icp_name    = self._derive_name(
                business_context or industry_fit, inferred_industries
            )
            icp_summary = self._derive_summary_advanced(
                business_context, industry_fit,
                target_geography, employee_range, pain_points
            )

            icp_data = {
                "business_context": {
                    "user_company_description": business_context or "Not specified",
                    "product_or_service":       business_context or "Not specified",
                    "primary_value_proposition": business_context or "Not specified",
                    "main_use_cases": (
                        self._split_or_wrap(pain_points) if pain_points
                        else ["Not specified"]
                    ),
                },
                "best_fit_industries": (
                    inferred_industries if inferred_industries
                    else self._split_or_wrap(industry_fit) or ["Not specified"]
                ),
                "acceptable_industries": [],
                "excluded_industries": ["Not specified"],
                "target_geography": {
                    "primary": (
                        self._split_or_wrap(target_geography) if target_geography
                        else ["Not specified"]
                    ),
                    "secondary": [],
                },
                "employee_range": {
                    "ideal":      employee_range or "Not specified",
                    "acceptable": employee_range or "Not specified",
                    "excluded":   "Not specified",
                },
                "revenue_range": revenue_or_budget or "Not specified",
                "company_stage": (
                    self._split_or_wrap(company_stage) if company_stage
                    else ["Not specified"]
                ),
                "business_model": ["B2B"],
                "technology_profile": {
                    "tools_they_may_use": (
                        self._split_or_wrap(tools_and_technology) if tools_and_technology
                        else ["Not specified"]
                    ),
                    "tools_that_increase_fit": (
                        self._split_or_wrap(tools_and_technology) if tools_and_technology
                        else ["Not specified"]
                    ),
                    "technology_maturity": "unknown",
                },
                "pain_and_use_case_fit": {
                    "primary_pain_points": (
                        self._split_or_wrap(pain_points) if pain_points
                        else inferred_keywords[:3] or ["Not specified"]
                    ),
                    "business_impact": ["Not specified"],
                    "best_entry_angle": (
                        pain_points[:150] if pain_points else "Not specified"
                    ),
                },
                "buying_signals": (
                    self._split_or_wrap(buying_signals) if buying_signals
                    else ["Not specified"]
                ),
                "buyer_committee": {
                    "recommended_first_contacts": inferred_roles or ["Not specified"],
                    "economic_buyer":   [],
                    "technical_buyer":  [],
                    "champion":         [],
                    "possible_blockers": [],
                },
                "disqualifiers": (
                    self._split_or_wrap(disqualifiers) if disqualifiers
                    else ["Not specified"]
                ),
                # Cannot derive priority segments without LLM reasoning.
                "priority_segments": [],
                "lead_scoring_rules": {
                    "industry_fit": (
                        f"High score for: {industry_fit}" if industry_fit
                        else "Not specified"
                    ),
                    "geography_fit": (
                        f"High score for: {target_geography}" if target_geography
                        else "Not specified"
                    ),
                    "company_size_fit": (
                        f"High score for: {employee_range}" if employee_range
                        else "Not specified"
                    ),
                    "revenue_fit": (
                        f"High score for: {revenue_or_budget}" if revenue_or_budget
                        else "Not specified"
                    ),
                    "technology_fit": (
                        f"High score for companies using: {tools_and_technology}"
                        if tools_and_technology else "Not specified"
                    ),
                    "pain_fit": (
                        f"High score for: {pain_points}" if pain_points
                        else "Not specified"
                    ),
                    "buying_signal_fit": (
                        f"High score for: {buying_signals}" if buying_signals
                        else "Not specified"
                    ),
                    "buyer_role_fit": (
                        f"High score when contact is: {buyer_roles}" if buyer_roles
                        else "Not specified"
                    ),
                    "disqualifier_check": (
                        f"Exclude: {disqualifiers}" if disqualifiers
                        else "Not specified"
                    ),
                },
                "product_usage_context": usage_goal or "Not specified",
            }

            search_recipe = {
                "include_filters": {
                    "industries": (
                        inferred_industries if inferred_industries
                        else self._split_or_wrap(industry_fit) or ["Not specified"]
                    ),
                    "locations": (
                        self._split_or_wrap(target_geography) if target_geography
                        else ["Not specified"]
                    ),
                    "employee_range": employee_range or "Not specified",
                    "revenue_range":  revenue_or_budget or "Not specified",
                    "company_stage":  (
                        self._split_or_wrap(company_stage) if company_stage else []
                    ),
                    "technologies": (
                        self._split_or_wrap(tools_and_technology)
                        if tools_and_technology else []
                    ),
                },
                "exclude_filters": {
                    "industries": [],
                    "company_sizes": [],
                    "conditions": (
                        self._split_or_wrap(disqualifiers) if disqualifiers else []
                    ),
                },
                "priority_filters": (
                    self._split_or_wrap(buying_signals) if buying_signals else []
                ),
                "buyer_title_filters": inferred_roles,
                "keyword_filters":     inferred_keywords,
                "buying_signal_filters": (
                    self._split_or_wrap(buying_signals) if buying_signals else []
                ),
                "plain_english_search_summary": self._derive_search_summary(
                    industry_fit or business_context,
                    target_geography,
                    employee_range,
                    pain_points,
                    inferred_roles,
                ),
            }

            advanced_fields = {
                "business context":    business_context,
                "industry fit":        industry_fit,
                "target geography":    target_geography,
                "employee range":      employee_range,
                "revenue / budget":    revenue_or_budget,
                "company stage":       company_stage,
                "pain points":         pain_points,
                "tools / technology":  tools_and_technology,
                "buying signals":      buying_signals,
                "buyer roles":         buyer_roles,
                "disqualifiers":       disqualifiers,
            }
            filled = sum(1 for v in advanced_fields.values() if v)
            score  = max(30, int((filled / 11) * 70))

            icp_quality = {
                "score": score,
                "strengths": [
                    f"'{k}' was provided"
                    for k, v in advanced_fields.items()
                    if v
                ],
                "weaknesses": [
                    "Generated using fallback profile — primary LLM generation failed.",
                    "AI enrichment (priority segments, inferred impact) is not available in fallback.",
                ],
                "missing_fields": [
                    k for k, v in advanced_fields.items() if not v
                ],
                "recommended_improvements": [
                    "Retry ICP generation to get the full AI-enriched output.",
                    "Ensure all key fields were answered before retrying.",
                ],
            }

        return ICPOutputData(
            mode=mode,
            icp_name=icp_name,
            icp_summary=icp_summary,
            icp_data=icp_data,
            search_recipe=search_recipe,
            icp_quality=icp_quality,
            generation_method="fallback_profile",
            needs_review=True,
        )

    # ------------------------------------------------------------------
    # Inference helpers — expanded and domain-agnostic
    # ------------------------------------------------------------------

    def _infer_industries(self, text: str) -> list[str]:
        if not text:
            return []
        c = text.lower()

        # Map keyword → canonical industry label(s).
        # Ordered from specific to generic so more specific matches win.
        keyword_map = [
            ("fintech",       ["Fintech", "Financial Technology"]),
            ("insurtech",     ["InsurTech", "Insurance Technology"]),
            ("healthtech",    ["Health Tech", "Digital Health"]),
            ("medtech",       ["Medical Technology", "Health Tech"]),
            ("edtech",        ["EdTech", "Education Technology"]),
            ("proptech",      ["PropTech", "Real Estate Technology"]),
            ("legaltech",     ["LegalTech", "Legal Technology"]),
            ("martech",       ["MarTech", "Marketing Technology"]),
            ("adtech",        ["AdTech", "Advertising Technology"]),
            ("hrtech",        ["HR Tech", "Human Resources Technology"]),
            ("regtech",       ["RegTech", "Regulatory Technology"]),
            ("saas",          ["SaaS", "B2B SaaS", "Cloud Software"]),
            ("software",      ["Software"]),
            ("technology",    ["Technology"]),
            ("tech",          ["Technology"]),
            ("it services",   ["IT Services"]),
            (" it ",          ["IT Services"]),
            ("cloud",         ["Cloud Services"]),
            ("cybersecurity", ["Cybersecurity"]),
            ("security",      ["Cybersecurity"]),
            ("ecommerce",     ["E-commerce"]),
            ("e-commerce",    ["E-commerce"]),
            ("retail",        ["Retail"]),
            ("logistics",     ["Logistics", "Supply Chain"]),
            ("supply chain",  ["Supply Chain", "Logistics"]),
            ("manufacturing", ["Manufacturing"]),
            ("construction",  ["Construction"]),
            ("real estate",   ["Real Estate"]),
            ("healthcare",    ["Healthcare"]),
            ("health",        ["Healthcare"]),
            ("medical",       ["Healthcare", "Medical"]),
            ("pharma",        ["Pharmaceuticals"]),
            ("financial",     ["Financial Services"]),
            ("banking",       ["Banking", "Financial Services"]),
            ("insurance",     ["Insurance"]),
            ("accounting",    ["Accounting", "Finance"]),
            ("legal",         ["Legal Services"]),
            ("consulting",    ["Consulting", "Professional Services"]),
            ("agency",        ["Agency"]),
            ("marketing",     ["Marketing"]),
            ("media",         ["Media", "Publishing"]),
            ("education",     ["Education"]),
            ("recruitment",   ["Recruitment", "HR"]),
            ("hr",            ["Human Resources"]),
            ("energy",        ["Energy"]),
            ("oil",           ["Oil & Gas"]),
            ("telecom",       ["Telecommunications"]),
            ("travel",        ["Travel & Hospitality"]),
            ("hospitality",   ["Hospitality"]),
            ("food",          ["Food & Beverage"]),
            ("agriculture",   ["Agriculture"]),
        ]

        seen   = set()
        result = []
        for keyword, labels in keyword_map:
            if keyword in c:
                for label in labels:
                    if label not in seen:
                        seen.add(label)
                        result.append(label)

        return result

    def _infer_roles(self, text: str) -> list[str]:
        if not text:
            return []
        c = text.lower()

        role_map = {
            "ceo":                    "CEO",
            "chief executive":        "CEO",
            "cto":                    "CTO",
            "chief technology":       "CTO",
            "coo":                    "COO",
            "chief operating":        "COO",
            "cfo":                    "CFO",
            "chief financial":        "CFO",
            "cmo":                    "CMO",
            "chief marketing":        "CMO",
            "ciso":                   "CISO",
            "chief information security": "CISO",
            "founder":                "Founder",
            "co-founder":             "Co-Founder",
            "owner":                  "Owner",
            "president":              "President",
            "vp engineering":         "VP Engineering",
            "vp operations":          "VP Operations",
            "vp sales":               "VP Sales",
            "vp marketing":           "VP Marketing",
            "vp finance":             "VP Finance",
            "vp product":             "VP Product",
            "head of engineering":    "Head of Engineering",
            "head of operations":     "Head of Operations",
            "head of sales":          "Head of Sales",
            "head of marketing":      "Head of Marketing",
            "head of finance":        "Head of Finance",
            "head of product":        "Head of Product",
            "head of it":             "Head of IT",
            "operations manager":     "Operations Manager",
            "operations director":    "Operations Director",
            "sales manager":          "Sales Manager",
            "sales director":         "Sales Director",
            "marketing manager":      "Marketing Manager",
            "it manager":             "IT Manager",
            "it director":            "IT Director",
            "product manager":        "Product Manager",
            "engineering manager":    "Engineering Manager",
            "finance manager":        "Finance Manager",
            "procurement":            "Procurement Manager",
            "revops":                 "RevOps Manager",
            "revenue operations":     "Revenue Operations Manager",
            "devops":                 "DevOps Engineer",
            "data":                   "Data Manager",
            "chief compliance":       "Chief Compliance Officer",
            "compliance officer":     "Chief Compliance Officer",
            "compliance manager":     "Compliance Manager",
            "head of risk":           "Head of Risk",
            "risk manager":           "Risk Manager",
            "general counsel":        "General Counsel",
            "legal":                  "Legal Counsel",
            "director of operations": "Director of Operations",
            "director of sales":      "Director of Sales",
            "director of marketing":  "Director of Marketing",
            "director of finance":    "Director of Finance",
            "director of it":         "Director of IT",
            "director of engineering":"Director of Engineering",
            "managing director":      "Managing Director",
            "partner":                "Partner",
            "principal":              "Principal",
        }

        seen   = set()
        result = []
        for keyword, label in role_map.items():
            if keyword in c and label not in seen:
                seen.add(label)
                result.append(label)

        if not result:
            result = ["Decision Maker", "Department Head"]

        return result

    def _infer_keywords(self, text: str) -> list[str]:
        if not text:
            return []
        c = text.lower()

        # Domain-agnostic keyword map — not automation-specific.
        keyword_map = {
            "manual":       "manual processes",
            "paperwork":    "manual paperwork",
            "data entry":   "data entry",
            "approval":     "slow approvals",
            "workflow":     "workflow inefficiency",
            "automation":   "automation",
            "operations":   "operational efficiency",
            "admin":        "administrative overhead",
            "disconnected": "disconnected systems",
            "process":      "process improvement",
            "cost":         "cost reduction",
            "speed":        "speed improvement",
            "scale":        "scaling operations",
            "growth":       "business growth",
            "funding":      "recently funded",
            "hiring":       "active hiring",
            "expansion":    "market expansion",
            "compliance":   "regulatory compliance",
            "security":     "security concerns",
            "integration":  "system integration",
            "reporting":    "reporting inefficiency",
            "visibility":   "lack of visibility",
            "collaboration": "team collaboration",
            "remote":       "remote work",
            "customer":     "customer experience",
            "retention":    "customer retention",
            "churn":        "churn reduction",
            "revenue":      "revenue growth",
            "pipeline":     "sales pipeline",
            "lead":         "lead generation",
            "outreach":     "outbound outreach",
        }

        seen   = set()
        result = []
        for key, label in keyword_map.items():
            if key in c and label not in seen:
                seen.add(label)
                result.append(label)

        return result

    # ------------------------------------------------------------------
    # Derivation helpers — build human-readable strings from answers
    # ------------------------------------------------------------------

    def _split_or_wrap(self, text: str) -> list[str]:
        """
        Converts a raw answer string to a list.
        Tries common delimiters; falls back to wrapping as a single item.
        """
        if not text or not text.strip():
            return []
        for delimiter in [",", ";", "\n", " / ", " | "]:
            if delimiter in text:
                parts = [p.strip() for p in text.split(delimiter) if p.strip()]
                if len(parts) > 1:
                    return parts
        return [text.strip()]

    def _normalize_size(self, size_text: str) -> str:
        """
        Converts colloquial size descriptions to a clean range string.
        If no pattern matches, returns the raw text unchanged.
        """
        if not size_text:
            return ""
        c = size_text.lower()
        if "small" in c and "mid" not in c and "large" not in c:
            return "1-50 employees"
        if "mid" in c or "medium" in c:
            return "50-300 employees"
        if "large" in c or "enterprise" in c:
            return "500+ employees"
        return size_text

    def _derive_name(self, context: str, industries: list[str]) -> str:
        """Builds a short ICP name from context and inferred industries."""
        if industries:
            industry_label = industries[0]
        elif context:
            industry_label = context[:40]
        else:
            return "ICP — Target Profile"

        return f"ICP: {industry_label} target profile"

    def _derive_summary_beginner(
        self,
        plain_target: str,
        location: str,
        company_size: str,
        problem: str,
    ) -> str:
        parts = []
        if plain_target:
            parts.append(f"Target: {plain_target}")
        if location:
            parts.append(f"in {location}")
        if company_size:
            parts.append(f"({self._normalize_size(company_size) or company_size})")
        if problem:
            parts.append(f"with a need for: {problem[:80]}")
        if not parts:
            return "Target profile based on collected answers — review recommended."
        return " ".join(parts) + "."

    def _derive_summary_advanced(
        self,
        business_context: str,
        industry_fit: str,
        geography: str,
        employee_range: str,
        pain_points: str,
    ) -> str:
        parts = []
        if industry_fit:
            parts.append(f"Targeting {industry_fit[:60]}")
        elif business_context:
            parts.append(f"Targeting companies that need: {business_context[:80]}")
        if geography:
            parts.append(f"in {geography}")
        if employee_range:
            emp = employee_range
            if "employee" not in emp.lower():
                emp = emp + " employees"
            parts.append(f"with {emp}")
        if pain_points:
            parts.append(f"experiencing: {pain_points[:80]}")
        if not parts:
            return "Target profile based on collected answers — review recommended."
        return " ".join(parts) + "."

    def _derive_search_summary(
        self,
        target: str,
        geography: str,
        size: str,
        pain_points: str,
        roles: list[str],
    ) -> str:
        parts = ["Find"]
        if target:
            parts.append(target[:60])
        else:
            parts.append("target companies")
        if geography:
            parts.append(f"in {geography}")
        if size:
            parts.append(f"with {self._normalize_size(size) or size}")
        if pain_points:
            parts.append(f"experiencing {pain_points[:60]}")
        if roles:
            parts.append(f"— contact: {', '.join(roles[:3])}")
        return " ".join(parts) + "."
"""
ICP → Company Search adapter.

Place at: app/ai/services/icp_search.py

WHAT THIS SOLVES
----------------
Your pipeline generates a `search_recipe`, but nothing consumes it. This module
is the missing link: it normalizes the recipe into a provider-agnostic filter
set, then hands it to a pluggable backend that actually runs the search.

TWO RECIPE SHAPES
-----------------
The ICPBuilder emits two different search_recipe shapes depending on mode:

  beginner (flat):
    include_industries, exclude_industries, locations,
    employee_range, keywords, buyer_roles, plain_english_search_summary

  advanced (nested):
    include_filters: {industries, locations, employee_range, revenue_range,
                      company_stage, technologies}
    exclude_filters: {industries, company_sizes, conditions}
    priority_filters, buyer_title_filters, keyword_filters,
    buying_signal_filters, plain_english_search_summary

`normalize_recipe()` flattens both into one SearchFilters object so downstream
backends never care which mode produced it.

BACKENDS
--------
  MockSearchBackend   — returns synthetic results. No API key. Use for demos
                        and for testing the wiring end-to-end.
  ApolloSearchBackend — real Apollo.io People/Organization search.

IMPORTANT: Apollo's API surface changes. The request shape below reflects their
documented mixed_companies/search and mixed_people/search endpoints, but you
MUST verify field names against https://docs.apollo.io before relying on it.
If a field name is wrong Apollo silently ignores it rather than erroring, which
produces confusingly broad results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Normalized filter model — provider agnostic
# ------------------------------------------------------------------

@dataclass
class SearchFilters:
    """
    One flat, provider-agnostic representation of a search_recipe.
    Every backend translates FROM this, never from the raw recipe.
    """
    include_industries: list[str] = field(default_factory=list)
    exclude_industries: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    employee_min: Optional[int] = None
    employee_max: Optional[int] = None
    employee_range_raw: str = ""
    revenue_range_raw: str = ""
    company_stages: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    buyer_titles: list[str] = field(default_factory=list)
    buying_signals: list[str] = field(default_factory=list)
    exclude_conditions: list[str] = field(default_factory=list)
    summary: str = ""

    def is_empty(self) -> bool:
        """True if there's nothing meaningful to search on."""
        return not any([
            self.include_industries, self.locations, self.keywords,
            self.buyer_titles, self.technologies,
            self.employee_min, self.employee_max,
        ])


# ------------------------------------------------------------------
# Recipe normalization
# ------------------------------------------------------------------

# Matches "51-300 employees", "1000+ employees", "under 50", "11 to 50"
_RANGE_PATTERNS = [
    (re.compile(r"(\d[\d,]*)\s*[-–—]\s*(\d[\d,]*)"), "range"),
    (re.compile(r"(\d[\d,]*)\s*to\s*(\d[\d,]*)", re.I), "range"),
    (re.compile(r"(\d[\d,]*)\s*\+"), "min_only"),
    (re.compile(r"over\s+(\d[\d,]*)", re.I), "min_only"),
    (re.compile(r"under\s+(\d[\d,]*)", re.I), "max_only"),
    (re.compile(r"less than\s+(\d[\d,]*)", re.I), "max_only"),
]


def parse_employee_range(text: str) -> tuple[Optional[int], Optional[int]]:
    """
    Extracts (min, max) headcount from free text.

    "51-300 employees"  -> (51, 300)
    "1000+ employees"   -> (1000, None)
    "under 50"          -> (None, 50)
    "mid-sized"         -> (None, None)   # no digits, caller falls back to raw
    """
    if not text:
        return None, None

    clean = text.replace(",", "")
    for pattern, kind in _RANGE_PATTERNS:
        m = pattern.search(clean)
        if not m:
            continue
        if kind == "range":
            return int(m.group(1)), int(m.group(2))
        if kind == "min_only":
            return int(m.group(1)), None
        if kind == "max_only":
            return None, int(m.group(1))
    return None, None


def _as_list(value: Any) -> list[str]:
    """Coerces a recipe value into a clean list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        # Drop the builder's placeholder so it never reaches a real query.
        return [] if not v or v.lower() == "not specified" else [v]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if isinstance(item, str):
                s = item.strip()
                if s and s.lower() != "not specified":
                    out.append(s)
            elif item is not None:
                out.append(str(item))
        return out
    if isinstance(value, dict):
        return [str(v) for v in value.values() if v]
    return [str(value)]


def normalize_recipe(search_recipe: dict) -> SearchFilters:
    """
    Flattens either recipe shape into SearchFilters.
    Detects the shape by presence of the nested 'include_filters' key.
    """
    if not isinstance(search_recipe, dict):
        return SearchFilters()

    f = SearchFilters()
    f.summary = str(search_recipe.get("plain_english_search_summary") or "")

    if "include_filters" in search_recipe:
        # ---- advanced (nested) ----
        inc = search_recipe.get("include_filters") or {}
        exc = search_recipe.get("exclude_filters") or {}

        f.include_industries = _as_list(inc.get("industries"))
        f.locations          = _as_list(inc.get("locations"))
        f.employee_range_raw = str(inc.get("employee_range") or "")
        f.revenue_range_raw  = str(inc.get("revenue_range") or "")
        f.company_stages     = _as_list(inc.get("company_stage"))
        f.technologies       = _as_list(inc.get("technologies"))

        f.exclude_industries = _as_list(exc.get("industries"))
        f.exclude_conditions = _as_list(exc.get("conditions"))

        f.buyer_titles   = _as_list(search_recipe.get("buyer_title_filters"))
        f.keywords       = _as_list(search_recipe.get("keyword_filters"))
        f.buying_signals = _as_list(search_recipe.get("buying_signal_filters"))
    else:
        # ---- beginner (flat) ----
        f.include_industries = _as_list(search_recipe.get("include_industries"))
        f.exclude_industries = _as_list(search_recipe.get("exclude_industries"))
        f.locations          = _as_list(search_recipe.get("locations"))
        f.employee_range_raw = str(search_recipe.get("employee_range") or "")
        f.keywords           = _as_list(search_recipe.get("keywords"))
        f.buyer_titles       = _as_list(search_recipe.get("buyer_roles"))

    f.employee_min, f.employee_max = parse_employee_range(f.employee_range_raw)
    return f


# ------------------------------------------------------------------
# Backend protocol
# ------------------------------------------------------------------

class SearchBackend(Protocol):
    """Any search provider implements this one method."""
    name: str

    def search(self, filters: SearchFilters, limit: int) -> list[dict]:
        ...


# ------------------------------------------------------------------
# Mock backend — no API key, deterministic, for demos + tests
# ------------------------------------------------------------------

class MockSearchBackend:
    """
    Generates plausible synthetic companies that satisfy the filters.

    This exists so the full pipeline (ICP -> recipe -> search -> results)
    is demonstrable and testable without any paid API. Results are clearly
    marked `"source": "mock"` so they can never be mistaken for real data.
    """
    name = "mock"

    _CITY_BY_REGION = {
        "united states": ["San Francisco, CA", "Austin, TX", "New York, NY", "Denver, CO"],
        "united kingdom": ["London, UK", "Manchester, UK", "Bristol, UK"],
        "canada": ["Toronto, ON", "Vancouver, BC"],
        "germany": ["Berlin, DE", "Munich, DE"],
        "france": ["Paris, FR", "Lyon, FR"],
        "australia": ["Sydney, NSW", "Melbourne, VIC"],
    }

    def search(self, filters: SearchFilters, limit: int = 10) -> list[dict]:
        industries = filters.include_industries or ["Technology"]
        locations = filters.locations or ["United States"]
        titles = filters.buyer_titles or ["VP Operations"]

        emp_min = filters.employee_min or 50
        emp_max = filters.employee_max or max(emp_min + 250, 300)

        results = []
        for i in range(limit):
            industry = industries[i % len(industries)]
            region = locations[i % len(locations)]
            city_pool = self._CITY_BY_REGION.get(region.lower(), [region])
            # Spread headcount deterministically across the range.
            span = max(emp_max - emp_min, 1)
            headcount = emp_min + (i * span // max(limit, 1))

            slug = re.sub(r"[^a-z0-9]+", "", industry.lower())[:10] or "co"
            results.append({
                "source": "mock",
                "company_name": f"{industry.split('/')[0].strip()} Co {i + 1}",
                "domain": f"{slug}{i + 1}.example.com",
                "industry": industry,
                "location": city_pool[i % len(city_pool)],
                "employee_count": headcount,
                "matched_keywords": filters.keywords[:3],
                "suggested_contact_title": titles[i % len(titles)],
                "match_reason": (
                    f"{industry} company in {region} with ~{headcount} employees"
                ),
                "confidence": round(0.9 - (i * 0.03), 2),
            })
        return results


# ------------------------------------------------------------------
# Apollo backend — real API
# ------------------------------------------------------------------

class ApolloSearchBackend:
    """
    Apollo.io organization search.

    Requires: pip install httpx
    Requires: APOLLO_API_KEY in your environment.

    VERIFY THE FIELD NAMES. Apollo's API evolves and, critically, it ignores
    unrecognized filter keys rather than rejecting them — so a stale field name
    produces a silently over-broad result set instead of an error. Check
    https://docs.apollo.io before trusting output in production.
    """
    name = "apollo"

    ORG_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"

    def __init__(self, api_key: str, timeout: float = 20.0):
        if not api_key:
            raise ValueError("ApolloSearchBackend requires an API key.")
        self.api_key = api_key
        self.timeout = timeout

    def _build_payload(self, filters: SearchFilters, limit: int) -> dict:
        payload: dict[str, Any] = {
            "page": 1,
            "per_page": min(limit, 100),  # Apollo caps per_page at 100
        }

        if filters.locations:
            payload["organization_locations"] = filters.locations

        # Apollo expects headcount as bucket strings like "51,200".
        if filters.employee_min is not None or filters.employee_max is not None:
            lo = filters.employee_min if filters.employee_min is not None else 1
            hi = filters.employee_max if filters.employee_max is not None else 100000
            payload["organization_num_employees_ranges"] = [f"{lo},{hi}"]

        # Industries + keywords both map to Apollo's keyword tag search.
        tags = filters.include_industries + filters.keywords + filters.technologies
        if tags:
            payload["q_organization_keyword_tags"] = tags[:20]

        return payload

    def search(self, filters: SearchFilters, limit: int = 10) -> list[dict]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError(
                "httpx is required for ApolloSearchBackend. "
                "Install it with: pip install httpx"
            ) from exc

        payload = self._build_payload(filters, limit)
        logger.info(f"APOLLO SEARCH | payload={payload}")

        try:
            resp = httpx.post(
                self.ORG_SEARCH_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "x-api-key": self.api_key,
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.error(f"Apollo search failed: {exc}")
            raise

        orgs = data.get("organizations") or data.get("accounts") or []
        results = []
        for org in orgs[:limit]:
            results.append({
                "source": "apollo",
                "company_name": org.get("name"),
                "domain": org.get("website_url") or org.get("primary_domain"),
                "industry": org.get("industry"),
                "location": ", ".join(
                    p for p in [org.get("city"), org.get("state"), org.get("country")] if p
                ),
                "employee_count": org.get("estimated_num_employees"),
                "linkedin_url": org.get("linkedin_url"),
                "matched_keywords": filters.keywords[:3],
                "suggested_contact_title": (
                    filters.buyer_titles[0] if filters.buyer_titles else None
                ),
                "match_reason": f"Apollo match on {org.get('industry') or 'keyword tags'}",
                "confidence": None,  # Apollo does not return a fit score here
                "raw": org,
            })
        return results


# ------------------------------------------------------------------
# Public entry point
# ------------------------------------------------------------------

def get_backend(name: str = "mock", api_key: str = "") -> SearchBackend:
    """Factory. Add new providers here."""
    if name == "apollo":
        return ApolloSearchBackend(api_key=api_key)
    if name == "mock":
        return MockSearchBackend()
    raise ValueError(f"Unknown search backend: {name}. Use 'mock' or 'apollo'.")


def search_from_recipe(
    search_recipe: dict,
    backend: str = "mock",
    api_key: str = "",
    limit: int = 10,
) -> dict:
    """
    Full path: raw search_recipe -> normalized filters -> provider -> results.

    Returns a dict containing the normalized filters (so you can see exactly
    what was searched on) alongside the results.
    """
    filters = normalize_recipe(search_recipe)

    if filters.is_empty():
        return {
            "backend": backend,
            "result_count": 0,
            "results": [],
            "filters_used": filters.__dict__,
            "warning": (
                "The search recipe contained no usable filters. "
                "This usually means the ICP was generated from very thin answers "
                "or fell back to a placeholder profile."
            ),
        }

    impl = get_backend(backend, api_key)
    results = impl.search(filters, limit)

    return {
        "backend": impl.name,
        "result_count": len(results),
        "results": results,
        "filters_used": filters.__dict__,
    }

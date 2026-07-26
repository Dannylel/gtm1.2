# GTM AI — ICP Builder

An LLM-driven conversational tool that interviews a user about their target market, generates a structured **Ideal Customer Profile (ICP)** and a **ready search recipe**, stores everything for evaluation, and exports a Word report.

---

## Table of contents

1. [What this actually does](#1-what-this-actually-does)
2. [Architecture](#2-architecture)
3. [Requirements](#3-requirements)
4. [Installation](#4-installation)
5. [Configuration — every knob](#5-configuration--every-knob)
6. [Running the app](#6-running-the-app)
7. [Usage — the three modes](#7-usage--the-three-modes)
8. [The verification step](#8-the-verification-step)
9. [Understanding the output](#9-understanding-the-output)
10. [Company search (ICP → target list)](#10-company-search-icp--target-list)
11. [The observability dashboard](#11-the-observability-dashboard)
12. [Full API reference](#12-full-api-reference)
13. [The database](#13-the-database)
14. [Testing](#14-testing)
15. [Customization guide](#15-customization-guide)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. What this actually does

A user opens a chat interface and picks how they want to build their ICP. The backend runs an LLM-driven conversation, extracts structured targeting criteria from their answers, shows them a summary to confirm, then generates:

- **An ICP profile** — industries, geography, company size, buyer roles, pain points, buying signals, disqualifiers
- **A search recipe** — the same information reshaped into filters you can hand to a company database
- **A quality score** — how complete and actionable the profile is
- **A Word report** — the whole thing as a downloadable `.docx`

The key design principle: **the frontend is dumb, the backend owns the workflow, and the LLM only generates content.** The chat UI just displays messages and sends text. All state, all branching, all decisions live server-side.

---

## 2. Architecture

```
chat.html  (dumb terminal — displays messages, sends text)
    │
    ▼
FastAPI route  (app/api/ai_routes.py — thin, no logic)
    │
    ▼
OnboardingService  (the state machine — owns all workflow decisions)
    │
    ├──► GeminiProvider.chat()               → free-text conversation turns
    │
    └──► ICPBuilder.build_from_answers()
             │
             └──► GeminiProvider.generate_structured()  → the final ICP JSON
                      │
                      ▼
                 Pydantic validates
                      │
                      ▼
                 Database stores
                      │
                      ▼
                 ReportGenerator → .docx
```

### The pieces

| File | Role |
|---|---|
| `app/main.py` | App startup, CORS, table creation, serves the chat UI |
| `app/api/ai_routes.py` | Onboarding endpoints. Thin — delegates to the service |
| `app/api/dashboard_routes.py` | Observability metrics + event browser |
| `app/api/search_routes.py` | Turns a search recipe into a company list |
| `app/ai/services/onboarding_service.py` | **The core.** Session state machine, all three modes, confirmation, finalization |
| `app/ai/services/icp_builder.py` | Builds the ICP generation prompts, calls the LLM, provides the fallback profile |
| `app/ai/services/icp_search.py` | Normalizes a search recipe and runs it against a provider |
| `app/ai/services/report_generator.py` | Renders the `.docx` report |
| `app/ai/services/plan_recommender.py` | Standalone pricing-tier suggestion (separate from the ICP flow) |
| `app/ai/providers/gemini_provider.py` | OpenRouter client. `chat()` for conversation, `generate_structured()` for JSON |
| `app/ai/config/icp_questions.py` | Question definitions and UI hints for each field |
| `app/ai/schemas/onboarding.py` | Pydantic request/response models |
| `app/ai/observability/generation_events.py` | Failure categories and weighted completeness scoring |
| `app/db/models.py` | SQLAlchemy tables |
| `app/db/database.py` | Engine and session factory |
| `app/core/config.py` | Settings, loaded from `.env` |
| `app/static/chat.html` | The chat UI |
| `app/static/dashboard.html` | The observability UI |

### Session state machine

A session moves through these `status` values:

```
mode_selection
      │
      ▼
in_progress ──────────────────────────┐
      │                               │  (advanced only)
      │                               ▼
      │                      optional_continuation
      │                               │
      │                               ▼
      │                    optional_answering:{field}
      │                               │
      ▼                               │
pending_confirmation  ◄───────────────┘
      │
      ├── user says "yes"  ──► completed
      └── user requests change ──► back to in_progress
```

---

## 3. Requirements

- **Python 3.10+** (3.12 recommended — `X | None` union syntax is used)
- **An OpenRouter account** — https://openrouter.ai. Free-tier models work.
- ~200 MB disk for dependencies

No database server needed. SQLite is used by default and creates itself.

---

## 4. Installation

### 4.1 Get the code

```bash
cd your-workspace
# clone or copy the project, then:
cd gtm-ai-backend
```

### 4.2 Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Windows (cmd):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)`.

### 4.3 Install dependencies

```bash
pip install fastapi uvicorn sqlalchemy pydantic pydantic-settings python-dotenv openai python-docx httpx
```

Or, if a `requirements.txt` exists:
```bash
pip install -r requirements.txt
```

**What each is for:**

| Package | Why |
|---|---|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM |
| `pydantic`, `pydantic-settings` | Validation and settings |
| `python-dotenv` | Loads `.env` |
| `openai` | OpenRouter uses an OpenAI-compatible API |
| `python-docx` | Word report generation |
| `httpx` | Only needed for the Apollo search backend |

> On some Linux distros pip refuses to install without a flag. If you see "externally-managed-environment", add `--break-system-packages`.

### 4.4 Verify the folder structure

```
gtm-ai-backend/
├── .env                      ← you create this (step 5)
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── ai_routes.py
│   │   ├── dashboard_routes.py
│   │   └── search_routes.py
│   ├── ai/
│   │   ├── config/icp_questions.py
│   │   ├── observability/
│   │   │   ├── __init__.py          ← must exist (can be empty)
│   │   │   └── generation_events.py
│   │   ├── providers/gemini_provider.py
│   │   ├── schemas/onboarding.py
│   │   └── services/
│   │       ├── icp_builder.py
│   │       ├── icp_search.py
│   │       ├── onboarding_service.py
│   │       ├── plan_recommender.py
│   │       └── report_generator.py
│   ├── core/config.py
│   ├── db/
│   │   ├── database.py
│   │   └── models.py
│   └── static/
│       ├── chat.html
│       └── dashboard.html
├── reports/                  ← auto-created
└── gtm_ai.db                 ← auto-created
```

Every package folder needs an `__init__.py` (may be empty). If you get `ModuleNotFoundError`, a missing `__init__.py` is the usual cause.

### 4.5 Get an OpenRouter API key

1. Sign up at https://openrouter.ai
2. Go to **Keys** → **Create Key**
3. Copy it (starts with `sk-or-v1-`)

Free models are billed against a small free allowance. If you hit `402 insufficient credits`, either add credit or switch to a different free model.

---

## 5. Configuration — every knob

Create a `.env` file in the project root. **Every setting in `app/core/config.py` can be overridden by an uppercase env var of the same name.**

```dotenv
# ─── Required ──────────────────────────────────────────────
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# ─── Models ────────────────────────────────────────────────
AI_CHAT_CHAT_MODEL=google/gemini-2.5-flash
AI_CHAT_ROUTER_MODEL=google/gemini-2.5-flash

# ─── Token budgets ─────────────────────────────────────────
AI_CHAT_REPLY_MAX_TOKENS=1000
AI_STRUCTURED_MAX_TOKENS=4096

# ─── App ───────────────────────────────────────────────────
APP_NAME=GTM AI Backend
APP_ENV=development
APP_SITE_URL=http://localhost:8000
APP_SITE_NAME=GTM AI ICP Builder

# ─── Storage ───────────────────────────────────────────────
DATABASE_URL=sqlite:///./gtm_ai.db
REPORTS_DIR=reports

# ─── CORS ──────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# ─── Optional: company search ──────────────────────────────
APOLLO_API_KEY=
```

### Setting reference

| Variable | Default | What it controls |
|---|---|---|
| `OPENROUTER_API_KEY` | *(hardcoded fallback — replace it)* | Your OpenRouter key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API endpoint. Change only to proxy. |
| `AI_CHAT_CHAT_MODEL` | `google/gemini-2.5-flash` | Model for conversation turns **and** ICP generation |
| `AI_CHAT_ROUTER_MODEL` | same | **Currently unused** (see [fat audit](#fat-audit)) |
| `AI_CHAT_REPLY_MAX_TOKENS` | `1000` | Cap on a single conversational reply. Raise if replies truncate mid-sentence. |
| `AI_STRUCTURED_MAX_TOKENS` | `4096` | Starting budget for ICP JSON. The provider escalates (4096 → 6144 → 8192 → 12000) if output is truncated. |
| `DATABASE_URL` | `sqlite:///./gtm_ai.db` | Any SQLAlchemy URL. Postgres: `postgresql://user:pass@host/db` |
| `REPORTS_DIR` | `reports` | Where `.docx` files are written |
| `CORS_ORIGINS` | localhost:3000,5173 | Comma-separated allowed origins |
| `APP_ENV` | `development` | Shown in `/health`. No behavioral effect. |
| `APOLLO_API_KEY` | *(empty)* | Only needed for the Apollo search backend |

### Choosing a model

Any OpenRouter model works. Trade-offs:

| Model | Cost | Instruction-following | Notes |
|---|---|---|---|
| `google/gemini-2.5-flash` | Low | Good | Recommended default |
| `google/gemini-2.5-flash:free` | Free | Good | Rate-limited |
| `anthropic/claude-sonnet-4` | Higher | Excellent | Best `<FIELD:>` tag compliance |
| `nvidia/nemotron-...:free` | Free | Variable | May ignore formatting instructions |

**Model slug format matters.** `google/gemini-2.5-flash:free` is valid. `google/gemini-2.5-flash: free` (with spaces) is **not** and will fail.

Weaker models frequently skip the `<FIELD:>` tags that drive the UI buttons — see [Troubleshooting](#16-troubleshooting).

### Hard-coded constants

Not in `.env` — edit the source directly:

| Constant | File | Default | Effect |
|---|---|---|---|
| `ADVANCED_MAX_QUESTIONS` | `onboarding_service.py` | `5` | Questions before the optional-continuation menu |
| `MAX_TURNS` | `onboarding_service.py` | `20` | Hard cap on conversational turns |
| `FIELD_WEIGHTS` | `generation_events.py` | see file | Per-field importance for the insufficient-info check |
| Insufficient-info threshold | `onboarding_service.py` `_finalize` | `0.25` | Below this weighted completeness, the LLM call is skipped |
| `_STRUCTURED_REASONING_TOKENS` | `gemini_provider.py` | `1024` | Caps thinking tokens so reasoning can't starve the JSON |

---

## 6. Running the app

```bash
uvicorn app.main:app --reload
```

Expected startup output:

```
CHAT MODEL: google/gemini-2.5-flash
MAX TOKENS: 1000
ENV KEY LOADED (last 8): ...abc12345
INFO: Settings loaded — API key ending: ...abc12345
INFO: APPLICATION STARTING
INFO: Uvicorn running on http://127.0.0.1:8000
```

If `CHAT MODEL` shows `NOT SET`, your `.env` isn't being read — check it's in the directory you launched uvicorn from.

### URLs

| URL | What |
|---|---|
| http://localhost:8000/chat | The chat UI — start here |
| http://localhost:8000/dashboard | Observability dashboard |
| http://localhost:8000/docs | Auto-generated Swagger API docs |
| http://localhost:8000/health | Health check |

### Other run options

```bash
uvicorn app.main:app --reload --port 8080          # different port
uvicorn app.main:app --host 0.0.0.0                # expose on network
uvicorn app.main:app --log-level debug             # verbose logs
uvicorn app.main:app                               # no auto-reload
```

---

## 7. Usage — the three modes

Open http://localhost:8000/chat, optionally enter an email and business name, click **Start Chat**. You'll be asked to pick a mode.

### Mode selection

You can click a button, type `1`/`2`/`3`, or type a word like `detailed`, `quick`, `chat`. Detection is regex-based with prefix matching, so `detail`, `detailed`, and `detailing` all select Detailed mode.

**Or skip mode selection entirely** — just type what you're looking for ("find me SaaS companies in Berlin") and it starts Quick mode with that as your first answer.

---

### Mode 1 — Quick (beginner)

**3 fixed questions. No LLM during the conversation.**

| # | Question | Input type |
|---|---|---|
| 1 | What does your company sell, and what problem does it solve? | Free text |
| 2 | What size companies are you targeting? | **Radio buttons** (5 bands) |
| 3 | Who usually makes the purchase decision? | **Checkboxes** (8 roles) |

Fast and predictable. The LLM is only called once, at the end, to generate the ICP.

**Try:** `We sell inventory management software for restaurants` → click *Small (11–50)* → check *Owner / Founder* and *Head of Operations*.

---

### Mode 2 — Detailed (advanced)

**Exactly 5 LLM-driven questions, then an optional deep-dive menu.**

Question 1 is always business context. The LLM then picks the 4 most relevant follow-ups from 11 available topics based on what you said. A fintech answer steers toward compliance; an SMB answer steers toward pain points and geography.

At least 2 of the 5 questions come with **quick-select buttons** so you're not typing everything.

After question 5 you get a menu:

```
I have a solid foundation for your ICP.
You can generate it now, or go deeper on one more area first:

  [ Revenue range & budget ]  [ Tools & technology stack ]
  [ Buying signals & triggers ]  [ Companies to exclude ]
  [ Generate ICP now → ]
```

Pick one optional topic, or generate immediately.

**Try:** `We sell an AI contract review platform for legal teams — cuts review time 60%` and follow the prompts.

---

### Mode 3 — Conversational

**Free-form chat. No fixed question count.**

The LLM covers topics in a priority order but adapts to how you talk:

- **Priority** (first): business context → industries + geography → size + stage
- **Variance** (next): pain points, buyer roles
- **Branch** (only if needed): revenue, tools, buying signals, disqualifiers, usage goal

It stops when it has enough, when you say so, or at 20 turns.

**Answer everything at once:** paste a dense paragraph covering all topics and it should generate on the very next turn.

**Force generation any time:** type `just generate it`, `go ahead`, `that's enough`, or `generate the ICP now`. Recognized by regex, so phrasing is flexible.

**Coverage score:** at the confirmation step this mode shows how complete your answers were:

```
📊 Coverage: 78% — High coverage (3/3 priority topics, 2/2 variance topics)
```

| Score | Label |
|---|---|
| 90–100 | Perfect coverage |
| 70–89 | High coverage |
| 50–69 | Average coverage |
| 30–49 | Low coverage |
| 0–29 | Minimal coverage |

This is **display only** — it does not trigger generation.

---

## 8. The verification step

Before any ICP is generated, **every mode** shows you what was captured:

```
Here's what I've gathered. Please review before I generate your ICP:

• What you sell: AI contract review platform for legal teams
• Target industries: Legal / Compliance, Financial Services
• Geography: United States, United Kingdom
• Company size: 200-2000 employees
• Buyer roles: General Counsel, VP Legal
...

Reply yes to generate your ICP, or tell me what to change.
```

- **"yes"** (or `ok`, `correct`, `looks good`, `proceed`, `generate`, `perfect`…) → generates
- **Anything else** → treated as a correction
  - *Quick mode:* restarts the 3 questions
  - *Detailed / Conversational:* your correction goes back to the LLM, which revises and re-presents

**Try a correction:** `Actually change the geography to Germany and France only`

---

## 9. Understanding the output

Four blocks render when generation completes.

### ICP Name & Summary
Short label plus a plain-English paragraph.

### ICP Profile (`icp_data`)
The full structured profile. Advanced mode includes business context, best-fit/acceptable/excluded industries, geography (primary/secondary), employee range (ideal/acceptable/excluded), revenue range, company stage, technology profile, pain points, buying signals, buyer committee, disqualifiers, priority segments, lead scoring rules.

### Ready Search Recipe (`search_recipe`)
The same data as **filters**. This is what feeds [company search](#10-company-search-icp--target-list).

Two shapes:
- *Beginner (flat)*: `include_industries`, `exclude_industries`, `locations`, `employee_range`, `keywords`, `buyer_roles`
- *Advanced (nested)*: `include_filters{}`, `exclude_filters{}`, `priority_filters`, `buyer_title_filters`, `keyword_filters`, `buying_signal_filters`

### ICP Quality Review (`icp_quality`)

Scored 0–100 against a rubric:

| Dimension | Weight | Measures |
|---|---|---|
| Completeness | 40 pts | What fraction of fields have substantive answers |
| Specificity | 30 pts | Precise vs vague. `51-300 employees` scores high; `medium companies` scores low |
| Actionability | 30 pts | Can these filters actually query a company database |

Plus ±5 for internal consistency (e.g. "enterprise companies" + "under $1M ARR" is contradictory).

Also lists `strengths`, `weaknesses`, `missing_fields`, `recommended_improvements`.

### Generation details

- `generation_method`: `gemini_structured_output` (LLM succeeded) or `fallback_profile` (it didn't)
- `needs_review`: whether a human should check it

### The fallback profile

If generation fails, a **deterministic, answers-first** profile is built in pure Python. It uses *your actual answers* — no hardcoded content. Anything you didn't provide shows `"Not specified"`.

`fallback_reason` tells you why:

| Reason | Meaning | Whose problem |
|---|---|---|
| `insufficient_info` | Too few / low-weight answers. LLM was never called. | User input |
| `provider_error` | The API call threw | Dependency |
| `timeout` | Call timed out | Dependency |
| `rate_limit` | 429 / quota exceeded | Dependency |
| `schema_invalid` | LLM replied but output failed validation | Prompt or model |
| `both_models_down` | Primary and backup both failed | Infrastructure |
| `unknown` | Uncategorized — investigate | ? |

### The Word report

Click **Download Word Report**. Contains: title page, executive summary, your inputs, generated ICP, search recipe, quality review, database records created, tagged evaluation examples, and a blank client review table.

Also available at `GET /ai/onboarding/report/{session_id}`.

---

## 10. Company search (ICP → target list)

> **This was the missing link.** Before this module, the pipeline generated a search recipe that nothing consumed.

### Setup

Add to `app/main.py`:

```python
from app.api.search_routes import router as search_router
app.include_router(search_router)
```

### Backends

| Backend | Key required | Use for |
|---|---|---|
| `mock` | No | Demos, testing the wiring. Returns synthetic results tagged `source: "mock"` |
| `apollo` | `APOLLO_API_KEY` | Real Apollo.io organization search |

### Search from a completed session

```bash
curl -X POST http://localhost:8000/search/from-session/YOUR_SESSION_ID \
  -H "Content-Type: application/json" \
  -d '{"backend": "mock", "limit": 10}'
```

```json
{
  "backend": "mock",
  "result_count": 10,
  "results": [
    {
      "source": "mock",
      "company_name": "Legal Co 1",
      "domain": "legalcompl1.example.com",
      "industry": "Legal / Compliance",
      "location": "London, UK",
      "employee_count": 200,
      "suggested_contact_title": "General Counsel",
      "match_reason": "Legal / Compliance company in United Kingdom with ~200 employees",
      "confidence": 0.9
    }
  ],
  "filters_used": { "...": "the normalized filters" },
  "icp_context": { "icp_name": "...", "mode": "advanced" }
}
```

### Debug why a search returned nothing

```bash
curl -X POST http://localhost:8000/search/preview-filters \
  -H "Content-Type: application/json" \
  -d '{"search_recipe": { ... }}'
```

Shows exactly which filters were extracted. `is_empty: true` means the recipe had no usable filters — usually because the ICP fell back to a placeholder.

### How normalization works

Both recipe shapes flatten into one `SearchFilters` object, so backends never care which mode produced the recipe. Headcount strings are parsed into integers:

| Input | Parsed |
|---|---|
| `"51-300 employees"` | `(51, 300)` |
| `"1000+ employees"` | `(1000, None)` |
| `"under 50"` | `(None, 50)` |
| `"11 to 50"` | `(11, 50)` |
| `"1,000-5,000"` | `(1000, 5000)` |
| `"mid-sized"` | `(None, None)` |

`"Not specified"` values are stripped so placeholders never reach a real query.

### Adding another provider

Implement one method in `icp_search.py`:

```python
class MyBackend:
    name = "mybackend"

    def search(self, filters: SearchFilters, limit: int) -> list[dict]:
        # translate `filters` into your provider's query, return list of dicts
        ...
```

Then register it in `get_backend()`.

> ⚠️ **Apollo caveat:** Apollo *silently ignores* unrecognized filter keys rather than erroring. A stale field name yields a confusingly broad result set instead of a clear failure. Verify field names against https://docs.apollo.io before trusting production output.

---

## 11. The observability dashboard

Visit http://localhost:8000/dashboard

### Overview page

Four cards: fallback rate (green under 10%, amber above), error rate (green under 5%, red above), p95 latency, total events. Three summary tables: fallback reasons, per-model reliability, distribution by mode.

### Events page

Seven combinable filters: outcome, fallback reason, mode, session ID, min latency, max quality score, time window.

Sortable columns (click any header). Click a row to expand — shows model used, backup flag, retry count, token split, session metadata, error detail, and the full answers that were fed into generation.

Paginated 50 at a time.

### What to watch

| Signal | Meaning |
|---|---|
| Fallback rate climbing | Model degrading, or users giving thinner answers |
| Mostly `insufficient_info` | UX problem — your questions aren't eliciting enough |
| Mostly `rate_limit` | Free model saturated. Switch models or add credit. |
| Mostly `schema_invalid` | Prompt or model problem. The model isn't producing valid output. |
| One model with a much higher fallback rate | Switch to the more reliable one |
| p95 latency rising | Provider under load |

**Set thresholds relative to a baseline, not from thin air.** Measure your normal rate for a week first. If you normally fall back 8% of the time on a free model, your alert threshold is "meaningfully above 8%", not "above 0%".

---

## 12. Full API reference

### Onboarding

#### `POST /ai/onboarding/start`
```json
{ "email": "user@example.com", "business_name": "Acme Corp" }
```
Both optional. Returns a `session_id` and the mode-selection message.

#### `POST /ai/onboarding/message`
```json
{ "session_id": "uuid", "message": "your answer" }
```
The main conversation endpoint. Behavior depends on session status.

Response:
```json
{
  "session_id": "uuid",
  "status": "in_progress",
  "mode": "advanced",
  "current_step": 2,
  "question": "Which industries are your best fit?",
  "question_key": "industry_fit",
  "mode_instruction": null,
  "icp_output": null,
  "report_path": null,
  "report_download_url": null,
  "ui_hint": {
    "type": "checkbox",
    "allow_custom": true,
    "options": [{ "label": "SaaS / Software", "value": "SaaS / Software" }]
  }
}
```

**`ui_hint` shape:**

| Field | Values | Meaning |
|---|---|---|
| `type` | `radio` \| `checkbox` \| `dropdown` | Control to render |
| `allow_custom` | `true` \| `false` | `false` hides the text input entirely |
| `options` | `[{label, value}]` | `label` is displayed, `value` is sent back |

`null` means free text only.

#### `GET /ai/onboarding/session/{session_id}`
Full session summary including all answers.

#### `GET /ai/onboarding/report/{session_id}`
Downloads the `.docx`.

#### `POST /ai/icp/build`
```json
{ "mode": "advanced", "answers": { "business_context": "...", "industry_fit": "..." } }
```
Generates an ICP directly from an answers dict. No session, no conversation. Useful for batch generation and testing prompt changes.

#### `POST /ai/plan/recommend`
```json
{ "team_size": 5, "expected_monthly_company_searches": 8000, "salesforce_required": false }
```
Rule-based pricing tier suggestion. Independent of the ICP flow.

### Search

| Endpoint | Purpose |
|---|---|
| `GET /search/backends` | List backends and availability |
| `POST /search/from-recipe` | Search using a recipe in the body |
| `POST /search/from-session/{id}` | Search using a session's stored ICP |
| `POST /search/preview-filters` | Normalize a recipe without searching |

### Dashboard

| Endpoint | Purpose |
|---|---|
| `GET /dashboard` | HTML UI |
| `GET /dashboard/metrics?hours=24` | Aggregate metrics JSON |
| `GET /dashboard/events?outcome=fallback&mode=advanced` | Filtered event list |
| `GET /dashboard/events/{id}` | Single event with session answers |

### System

| Endpoint | Purpose |
|---|---|
| `GET /health` | Health check |
| `GET /chat` | Chat UI |
| `GET /docs` | Swagger |

---

## 13. The database

SQLite at `./gtm_ai.db` by default. Tables are created automatically on startup — **no migrations needed**. New tables appear on restart; existing data is untouched.

| Table | Contents |
|---|---|
| `users` | Optional email / business name |
| `onboarding_sessions` | Session state: status, mode, step, report path |
| `onboarding_answers` | One row per captured field |
| `conversation_turns` | Raw chat transcript (advanced/conversational only) |
| `icp_profiles` | Generated ICP, search recipe, quality review |
| `generation_events` | **Observability** — one row per generation attempt |
| `token_usage_logs` | One row per LLM call with token counts and latency |
| `ai_dataset_examples` | Tagged input/output pairs for evaluation and fine-tuning |
| `plan_recommendations` | Defined but **never written to** |

### Inspecting it

```bash
python -m sqlite3 gtm_ai.db
```

```sql
.tables
SELECT outcome, fallback_reason, mode, latency_ms FROM generation_events ORDER BY created_at DESC LIMIT 20;

-- fallback rate
SELECT COUNT(*) total,
       SUM(outcome='fallback') fallbacks,
       ROUND(SUM(outcome='fallback')*100.0/COUNT(*),1) pct
FROM generation_events;

-- token spend per session
SELECT session_id, SUM(total_tokens) FROM token_usage_logs GROUP BY session_id;
.quit
```

GUI alternatives: [DB Browser for SQLite](https://sqlitebrowser.org/), or the SQLite extension in VSCode.

### Resetting

```bash
# stop the server first
rm gtm_ai.db      # Windows: del gtm_ai.db
uvicorn app.main:app --reload
```

### Switching to Postgres

```dotenv
DATABASE_URL=postgresql://user:password@localhost:5432/gtm_ai
```
```bash
pip install psycopg2-binary
```

Note: the dashboard computes latency percentiles in Python (SQLite has no `PERCENTILE` function). On Postgres you can replace that with a native `percentile_cont` query.

---

## 14. Testing

```bash
pip install pytest
```

### Tier 3 — live LLM compliance tests

These hit the real API. Run manually, never in CI.

```bash
pytest tests/test_live/ -v -s --tb=short
```

`-s` prints the model's actual replies so you can read them.

| Test class | Checks |
|---|---|
| `TestModelAvailability` | Model responds; latency under 30s |
| `TestFieldTagging` | Model emits `<FIELD: key>` tags (these drive the UI buttons) |
| `TestSingleQuestionPerTurn` | Doesn't dump a numbered list of questions |
| `TestICPReadyEmission` | Emits `<ICP_READY>` with parseable, non-placeholder JSON |
| `TestCorrectionHandling` | Re-emits a corrected `<ICP_READY>` after a change request |
| `TestOnTopicBehavior` | Steers back after an off-topic message |
| `TestTokenEfficiency` | Replies under 300 tokens; ICP_READY under 800 |

Run just the health check first:
```bash
pytest tests/test_live/ -v -s -k "TestModelAvailability"
```

**Interpreting failures** — each maps to an action:

| Failure | Do this |
|---|---|
| Field tagging fails | Model ignores formatting. Try a stronger model. |
| ICP_READY skipped | Model asks follow-ups instead of finishing. Tighten the completion instruction. |
| Token efficiency fails | Model is verbose. Add a hard length rule to the style prompt. |
| Latency fails | Free model backend is slow. Try another. |

These are **non-deterministic**. Assertions check *structural properties* (tag present, JSON parses, keys exist), never exact wording.

### Manual smoke test

1. `/chat` → Quick mode → 3 answers → confirm → ICP renders → download report
2. `/dashboard` → the event appears with `outcome: success`
3. `POST /search/from-session/{id}` with `backend: "mock"` → results returned
4. Repeat for Detailed and Conversational

---

## 15. Customization guide

### Change the questions

`app/ai/config/icp_questions.py`

```python
BEGINNER_QUESTIONS = [
    {
        "key": "my_new_field",              # must be unique
        "text": "Your question here?",
        "ui_hint": {                         # or None for free text
            "type": "radio",
            "allow_custom": True,
            "options": [{"label": "Shown to user", "value": "stored value"}],
        },
    },
]
```

Adding a field to `ADVANCED_QUESTIONS` also requires:
- a weight in `FIELD_WEIGHTS` (`generation_events.py`)
- a label in `_ADVANCED_TOPIC_LABELS` (`onboarding_service.py`)
- a label in `_format_icp_summary` (`onboarding_service.py`)

### Change question counts

```python
# onboarding_service.py
ADVANCED_MAX_QUESTIONS = 5   # advanced questions before the optional menu
MAX_TURNS = 20               # conversational hard cap
```

Beginner count = length of `BEGINNER_QUESTIONS`.

### Change the LLM's persona or rules

`_build_system_prompt()` in `onboarding_service.py`. Separate branches for advanced and conversational.

**Conditional navigation is written in plain English, not code:**

```
- If the user mentions a regulated industry (finance, healthcare, legal),
  ask about compliance requirements before asking about tools.
- If the company has fewer than 10 employees, skip revenue and stage.
```

The LLM interprets these contextually. This is the intended way to add branching logic.

### Change the ICP output shape

`_beginner_prompt()` / `_advanced_prompt()` in `icp_builder.py` contain the full JSON template. Edit the template **and** the matching branch in `fallback_profile()` so both stay in sync.

### Change the quality rubric

Both prompt methods in `icp_builder.py` contain the scoring rubric. Currently 40/30/30 completeness/specificity/actionability.

### Change fallback field weights

```python
# generation_events.py
FIELD_WEIGHTS = {
    "business_context": 10,   # without this there is no ICP
    "usage_goal": 1,          # barely affects ICP quality
}
```

And the threshold in `_finalize`:
```python
if completeness < 0.25:   # raise to be stricter about thin input
```

### Restyle the UI

`app/static/chat.html` and `dashboard.html` are standalone — CSS variables at the top of each `<style>` block.

---

## 16. Troubleshooting

### `ModuleNotFoundError: No module named 'app'`
Run uvicorn from the **project root** (the folder containing `app/`), not from inside `app/`.

### `ModuleNotFoundError: No module named 'app.ai.observability'`
Missing `__init__.py`. Every package folder needs one (may be empty).

### `ImportError: cannot import name 'GenerationEvent'`
Your `models.py` is an older version. Replace it and restart.

### Startup prints `CHAT MODEL: NOT SET`
`.env` isn't being read. It must be in the directory you launched uvicorn from. Verify with `dir .env` / `ls -la .env`.

### `402 — This request requires more credits`
Your OpenRouter balance is exhausted. **Rotating the API key does not help** — credits are tied to the account, not the key. Add credit, or switch to a `:free` model.

### `404 — No endpoints found`
Your model slug is wrong. Common cause: a space in the slug. `google/gemini-2.5-flash:free` ✓ — `google/gemini-2.5-flash: free` ✗

### Buttons don't appear; it asks for free text instead
The LLM didn't emit a `<FIELD: key>` tag, which is the only thing that triggers a UI hint.

Three causes:
1. **The model ignored the instruction** — most common with weak free models. Switch models.
2. **The field genuinely has no hint** — `business_context`, `pain_points`, and `disqualifiers` are deliberately free text. Working as intended.
3. **Malformed tag** — the regex needs `<FIELD: key>` exactly.

Diagnose by adding one line after tag extraction:
```python
logger.info(f"FIELD TAG | tail={reply[-80:]!r} extracted={field_key}")
```
Then check whether the tag is absent, malformed, or correctly pointing at a hint-less field.

### Every ICP falls back
Check the dashboard's fallback-reason breakdown first — it tells you which of these it is:
- `insufficient_info` → users aren't answering enough. Not a bug.
- `rate_limit` → free model saturated.
- `schema_invalid` → the model produces invalid JSON. Try a stronger model.
- `provider_error` → check the terminal traceback.

### Code changes don't take effect
1. Confirm you edited the file uvicorn actually loads — `python -c "import app.ai.services.onboarding_service as m; print(m.__file__)"`
2. Clear bytecode caches:
   ```cmd
   for /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"
   ```
   ```bash
   find . -name "__pycache__" -type d -exec rm -rf {} +
   ```
3. Fully restart uvicorn (Ctrl+C, then start again).

### Report download 404s
`reports/` may have been deleted, or `REPORTS_DIR` points somewhere unwritable. The path is stored per-session at generation time — moving files afterwards breaks the link.

### Getting the real error
Almost every failure prints a full traceback to the uvicorn terminal. Look for:
```
ERROR:app.ai.services.onboarding_service:advanced chat() failed:
ERROR:app.ai.services.onboarding_service:ICP generation error [reason]:
```
The categorized reason in brackets tells you which failure class it is.

---

## Fat audit

Dead or redundant code found by static analysis. **Nothing has been removed** — this is a list for you to decide on.

### Definitely dead

| What | Where | Evidence |
|---|---|---|
| `PLANS` dict | `plans.py` | **Never imported anywhere.** `PlanRecommender` hardcodes its own thresholds instead. The entire file is orphaned. |
| `ai_chat_router_model` | `config.py` | Declared and settable, never read by any code path. |
| `ai_router_max_tokens` | `config.py` | Commented out but the comment remains. |
| `CONVERSATIONAL_FIELD_KEYS` | `icp_questions.py` | Computed at import, never referenced. |
| `PlanRecommendation` table | `models.py` | Table is created but nothing ever inserts a row. The `/ai/plan/recommend` endpoint returns a response without persisting. |

### Oversized

| What | Size | Comment |
|---|---|---|
| `fallback_profile()` | **345 lines** | Largest method in the codebase. Beginner and advanced branches duplicate substantial structure. Could split into `_fallback_beginner()` / `_fallback_advanced()` with a shared quality-block builder. |
| `_advanced_prompt()` | 204 lines | Mostly a literal JSON template. If you adopt `json_schema` response format, most of the shape description becomes redundant and can be deleted. |
| `_beginner_prompt()` | 134 lines | Same. |
| `onboarding_service.py` | 1,201 lines, 34 methods | Doing three jobs: session state machine, LLM orchestration, and observability. The observability helpers (`_log_tokens`, `_record_generation_event`, `_categorize_failure`) could move to the observability module. |
| `icp_builder.py` | 1,018 lines | ~70% is prompt templates and the fallback. |

### Questionable value

| What | Comment |
|---|---|
| `_infer_industries` | 51 keyword patterns. Keyword matching has no context — "avoid retail" still matches Retail. Only runs in the fallback path. |
| `_infer_roles` / `_infer_keywords` | Same trade-off. Fallback-only. |
| `retry_count` on `GenerationEvent` | Always written as `0` — the provider's retry count is never plumbed through. Either wire it or drop the column. |
| `used_backup` on `GenerationEvent` | Always `"false"` — backup-model switching was designed but never built. |
| `plan_recommender.py` | Functional but entirely disconnected from the ICP flow. It's a separate product feature living in the same codebase. |

### Recommended order

1. **Delete `plans.py`** — zero risk, it's genuinely unreferenced.
2. **Delete `ai_chat_router_model`, `ai_router_max_tokens`, `CONVERSATIONAL_FIELD_KEYS`** — trivial.
3. **Decide on `plan_recommender`** — either wire it into the flow and persist to its table, or move it out.
4. **Split `fallback_profile()`** — biggest readability win.
5. **Wire or drop `retry_count` / `used_backup`** — columns that always hold the same value are misleading on a dashboard.

Leave the prompt templates alone until you decide on `json_schema` — that decision determines how much of them can go.

---

## Known gaps

| Gap | Status |
|---|---|
| Backup model switching | Designed, not built. `used_backup` always `false`. |
| `json_schema` response format | Discussed. Currently uses `json_object` + Pydantic validation. Blocked on the three freeform `dict[str, Any]` fields, which strict mode can't enforce. |
| Retry count plumbing | Provider retries internally but doesn't report the count upward. |
| Tier 1 / Tier 2 tests | Only Tier 3 (live) exists. |
| Contact enrichment | Search returns companies, not individual contacts. |
| Auth | None. Do not expose publicly as-is. |

---

## Security notes

- **`config.py` contains a hardcoded API key as a default value.** Replace it and rotate the key. Anyone who reads that file has your key.
- No authentication on any endpoint. `/dashboard` exposes session data and answers.
- CORS defaults to localhost. Update `CORS_ORIGINS` for real deployment.
- SQLite has no access control — the `.db` file is readable by anyone with filesystem access.

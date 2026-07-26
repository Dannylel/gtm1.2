# GTM AI ICP Builder

GTM AI ICP Builder is a FastAPI-based AI backend and demo chat UI for creating Ideal Customer Profiles (ICPs) and ready search recipes for a GTM / sales intelligence platform.

The current project uses **OpenRouter** with:

```env
AI_CHAT_CHAT_MODEL=google/gemini-2.5-flash
AI_CHAT_ROUTER_MODEL=google/gemini-2.5-flash
```

The chatbot converts user input into:

1. A structured ICP profile
2. A ready search recipe for the backend/search engine
3. An ICP quality review
4. A Word report for review/demo
5. Tagged dataset records for future evaluation or fine-tuning

---

## 1. Project Purpose

The chatbot is designed to enhance GTM's existing smart search system.

It does not replace manual filters. It helps users convert rough targeting ideas or detailed sales criteria into structured search-ready ICPs.

The system currently supports:

- Quick / Beginner ICP creation
- Detailed / Advanced ICP creation
- Search recipe generation
- ICP quality review
- Report generation
- Dataset logging
- Separate plan recommendation

---

## 2. Current Status

### Implemented

- FastAPI backend
- SQLite database
- OpenRouter-backed Gemini 2.5 Flash integration
- Chat UI at `/chat`
- Swagger docs at `/docs`
- Beginner mode
- Advanced mode
- ICP output generation
- Ready search recipe generation
- ICP quality review
- Word report generation
- Tagged dataset examples
- Separate plan recommendation endpoint

### Planned Later

- Mature ICP mode
- Upload existing ICP document
- Upload CRM/customer data
- Analyze best customer websites
- Lookalike ICP generation
- Real lead search execution
- Company enrichment
- Contact discovery
- Email generation pipeline integration
- CRM sync
- Authentication
- Human feedback loop
- Open-source model hosting / fine-tuning

---

## 3. Project Structure

```text
gtm-ai-backend/
│
├── app/
│   ├── main.py
│   │
│   ├── static/
│   │   └── chat.html
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py
│   │   └── models.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── ai_routes.py
│   │
│   └── ai/
│       ├── __init__.py
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── icp_questions.py
│       │   └── plans.py
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   └── gemini_provider.py
│       │
│       ├── schemas/
│       │   ├── __init__.py
│       │   └── onboarding.py
│       │
│       └── services/
│           ├── __init__.py
│           ├── icp_builder.py
│           ├── onboarding_service.py
│           ├── plan_recommender.py
│           └── report_generator.py
│
├── reports/
│   └── generated Word reports
│
├── .env
├── requirements.txt
<!-- ├── gtm_ai.db -->
└── README.md
```

---

## 4. Tech Stack

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- SQLite
- Pydantic
- Pydantic Settings
- OpenAI Python SDK
- OpenRouter API
- Gemini 2.5 Flash via OpenRouter
- python-docx
- HTML / CSS / JavaScript demo UI

---

## 5. Prerequisites

Install Python 3.10 or later.

Check Python version:

```bash
python --version
```

You also need an **OpenRouter API key**.

---

## 6. Setup Instructions

### Step 1: Clone Repository

```bash
git clone <your-repository-url>
cd gtm-ai-backend
```

### Step 2: Create Virtual Environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Create `.env`

Create a `.env` file in the project root.

```env
APP_NAME=GTM AI Backend
APP_ENV=development

DATABASE_URL=sqlite:///./gtm_ai.db

OPENROUTER_API_KEY=PASTE_YOUR_OPENROUTER_API_KEY_HERE
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

AI_CHAT_CHAT_MODEL=google/gemini-2.5-flash
AI_CHAT_ROUTER_MODEL=google/gemini-2.5-flash

AI_CHAT_MAX_TOKENS=4000
AI_ROUTER_MAX_TOKENS=1200

APP_SITE_URL=http://localhost:8000
APP_SITE_NAME=GTM AI ICP Builder

REPORTS_DIR=reports

CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173
```

Do **not** commit `.env` to GitHub.

### Step 5: Run Server

```bash
uvicorn app.main:app --reload
```

The backend will run at:

```text
http://127.0.0.1:8000
```

---

## 7. Requirements

Your `requirements.txt` should include:

```txt
fastapi
uvicorn[standard]
sqlalchemy
pydantic
pydantic-settings
python-dotenv
python-docx
openai
```

The project uses the `openai` package because OpenRouter exposes an OpenAI-compatible API.

---

## 8. Important URLs

### Health Check

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "env": "development",
  "service": "GTM AI Backend"
}
```

### Swagger API Docs

```text
http://127.0.0.1:8000/docs
```

### Chat UI

```text
http://127.0.0.1:8000/chat
```

---

## 9. API Endpoints

### Start ICP Chat

```http
POST /ai/onboarding/start
```

Example request:

```json
{
  "email": "optional@example.com",
  "business_name": "Optional Business Name"
}
```

Returns:

- session ID
- mode selection message
- current status

---

### Send Chat Message

```http
POST /ai/onboarding/message
```

Example request:

```json
{
  "session_id": "SESSION_ID_HERE",
  "message": "User answer here"
}
```

This endpoint:

- detects mode
- saves answers
- returns next question
- finalizes ICP after the final answer
- generates Word report
- saves tagged dataset examples

---

### Get Session Summary

```http
GET /ai/onboarding/session/{session_id}
```

Returns:

- session status
- selected mode
- all answers
- generated ICP output
- report path
- report download URL

---

### Download Word Report

```http
GET /ai/onboarding/report/{session_id}
```

Downloads the generated `.docx` report.

---

### Direct ICP Build

```http
POST /ai/icp/build
```

Example request:

```json
{
  "mode": "beginner",
  "answers": {
    "plain_target_description": "I want SaaS companies in New York.",
    "target_location": "New York, United States",
    "company_size": "50 to 300 employees",
    "problem_or_need": "Manual workflows and paperwork",
    "decision_maker": "CTO, COO, Founder"
  }
}
```

---

### Plan Recommendation

```http
POST /ai/plan/recommend
```

The plan recommender is separate from ICP generation.

Example request:

```json
{
  "team_size": 2,
  "expected_monthly_company_searches": 500,
  "expected_monthly_contacts": 150,
  "expected_monthly_emails": 500,
  "crm_required": false,
  "salesforce_required": false,
  "number_of_sending_domains": 1,
  "support_required": "standard"
}
```

---

## 10. Database

The app creates the database automatically on startup.

Database file:

```text
gtm_ai.db
```

### Tables

| Table | Purpose |
|---|---|
| `users` | Stores optional user email/business name |
| `onboarding_sessions` | Stores chat session, selected mode, status, current step, report path |
| `onboarding_answers` | Stores every question and answer |
| `icp_profiles` | Stores ICP output, search recipe, quality review |
| `ai_dataset_examples` | Stores tagged examples for evaluation/future fine-tuning |
| `plan_recommendations` | Stores plan recommendations only when the plan endpoint is called |

### Expected Rows After Beginner Session

| Table | Expected Rows |
|---|---:|
| `onboarding_sessions` | 1 |
| `onboarding_answers` | 5 |
| `icp_profiles` | 1 |
| `ai_dataset_examples` | 1 |
| `plan_recommendations` | 0 unless plan endpoint is called |

### Expected Rows After Advanced Session

| Table | Expected Rows |
|---|---:|
| `onboarding_sessions` | 1 |
| `onboarding_answers` | 12 |
| `icp_profiles` | 1 |
| `ai_dataset_examples` | 1 |
| `plan_recommendations` | 0 unless plan endpoint is called |

---

## 11. Chatbot Modes

Current active modes:

1. Quick / Beginner Mode
2. Detailed / Advanced Mode

Mature mode is planned for later.

---

## 12. Quick / Beginner Mode

### Purpose

Beginner mode is for users who describe their target audience in simple words.

The system creates:

- Beginner ICP
- Minimum viable lead record
- Ready search recipe
- ICP quality review

### Beginner Questions

1. Tell me in simple words what kind of companies you want to find.
2. Where should we search for these companies?
3. What size companies should we focus on: small, mid-sized, or large?
4. What problem should these companies have for your product or service to be useful?
5. Who would usually make the decision: owner, founder, operations head, CTO, sales head, or someone else?

### Beginner Test Answers

#### First Message / Mode Selection

Paste this directly after starting the chat:

```text
I want to find mid-sized B2B SaaS companies in New York that are growing and may need AI automation to reduce manual paperwork, repetitive workflows, and operational delays.
```

The system should automatically select Quick / Beginner Mode.

#### Answer 2

```text
New York, United States. We can also include nearby US-based SaaS companies if they match the same profile.
```

#### Answer 3

```text
Mid-sized companies, ideally 50 to 300 employees. They should be large enough to have operational workflows but not so large that sales cycles become too complex.
```

#### Answer 4

```text
They should have manual paperwork, repetitive data entry, slow approvals, disconnected tools, or operations teams spending too much time on routine admin work.
```

#### Answer 5

```text
The best first contacts are CTO, COO, Founder, Head of Operations, or Operations Manager. CTO is important for technical approval, while COO or Operations Head usually understands the workflow pain.
```

### Expected Beginner Output

The report should include:

- Mode: `beginner`
- ICP name related to mid-sized B2B SaaS companies needing AI automation
- Industry: Software / SaaS
- Location: New York, United States
- Company size: 50–300 employees
- Pain points:
  - manual paperwork
  - repetitive workflows
  - slow approvals
  - disconnected tools
  - routine admin work
- Buyer roles:
  - CTO
  - COO
  - Founder
  - Head of Operations
  - Operations Manager
- Ready search recipe:
  - SaaS / Software / B2B Software
  - New York / United States
  - 50–300 employees
  - automation / workflow / manual paperwork keywords
- ICP quality score ideally above 70

---

## 13. Detailed / Advanced Mode

### Purpose

Advanced mode is for users who can provide detailed targeting information.

The system creates:

- Fully enriched ICP
- Advanced ready search recipe
- Scoring logic
- Priority target segments
- ICP quality review

### Advanced Questions

1. What does your company sell, and what business problem does it solve?
2. Which industries are your best fit, which are acceptable, and which should be avoided?
3. Which countries, cities, or regions should GTM target first?
4. What employee range is ideal for your target companies?
5. What revenue range or customer budget level usually makes a company a good fit?
6. What stage should these companies be in: new, growing, scaling, funded, enterprise, expanding, or restructuring?
7. What problems should these companies be experiencing for your offer to be relevant?
8. Are there any tools, systems, or platforms they should already be using?
9. What signs would show that a company may need you right now?
10. Who should GTM contact first, and who else may influence the decision?
11. What type of companies should GTM avoid even if they match the basic filters?
12. How many companies, contacts, or outreach messages do you expect to work with each month?

### Advanced Test Answers

#### Mode Selection

After starting the chat, type:

```text
Detailed mode
```

#### Answer 1

```text
We sell AI automation systems for B2B companies. Our solution helps teams reduce manual paperwork, automate repetitive workflows, extract information from documents, streamline approvals, and reduce time spent on routine admin tasks.
```

#### Answer 2

```text
Best fit industries are B2B SaaS, IT services, business services, and operations-heavy technology companies. Acceptable industries are manufacturing, professional services, logistics, and fintech. Avoid consumer-only businesses, very small local businesses, restaurants, retail shops, and companies with no repeatable operational workflows.
```

#### Answer 3

```text
Primary target is New York, United States. Secondary target can be other major US business hubs such as Boston, San Francisco, Austin, and Chicago if the company matches the same profile.
```

#### Answer 4

```text
Ideal range is 50 to 300 employees. Acceptable range is 30 to 500 employees. Companies below 20 employees are usually too small, and companies above 1000 employees may have longer enterprise sales cycles.
```

#### Answer 5

```text
Ideal companies should have estimated annual revenue between 1 million and 50 million USD. They should have enough budget to invest in automation but still be growing enough to need practical efficiency improvements.
```

#### Answer 6

```text
Best-fit companies are growing or scaling. Strong signals include recently funded companies, companies expanding teams, companies entering new markets, or companies trying to improve operations before adding more headcount.
```

#### Answer 7

```text
Relevant problems include manual data entry, manual paperwork, slow internal approvals, document-heavy workflows, disconnected tools, repetitive admin work, lack of process automation, and operations teams spending too much time on low-value tasks.
```

#### Answer 8

```text
Good-fit companies may already use CRM, ERP, spreadsheets, HubSpot, Salesforce, QuickBooks, NetSuite, Slack, Google Workspace, Microsoft 365, Zapier, or Make. Existing use of multiple disconnected tools is a strong sign that automation may help.
```

#### Answer 9

```text
Strong buying signs include hiring operations roles, hiring RevOps or business operations roles, recent funding, new CTO or COO, expansion into new markets, job posts mentioning automation or process improvement, rapid headcount growth, or website content mentioning operational efficiency.
```

#### Answer 10

```text
First contacts should be CTO, COO, Founder, Head of Operations, VP Operations, or Operations Manager. CTO is important for technical fit, COO owns process efficiency, Founder cares about scaling, and Operations Manager can act as the internal champion. IT, finance, procurement, or legal may become blockers later.
```

#### Answer 11

```text
Avoid companies with fewer than 20 employees, companies outside SaaS or operations-heavy B2B industries, companies with no visible operational team, companies with no clear technology adoption, companies that only sell to consumers, and companies that appear too small to pay for automation.
```

#### Answer 12

```text
For now, we expect to search around 500 companies per month, shortlist 100 to 150 good-fit accounts, identify 2 to 3 contacts per account, and prepare around 300 to 500 personalized outreach messages per month.
```

### Expected Advanced Output

The report should include:

- Mode: `advanced`
- Best-fit industries:
  - B2B SaaS
  - IT services
  - business services
  - operations-heavy technology companies
- Acceptable industries:
  - manufacturing
  - professional services
  - logistics
  - fintech
- Excluded industries:
  - consumer-only businesses
  - very small local businesses
  - restaurants
  - retail shops
- Geography:
  - New York primary
  - Boston, San Francisco, Austin, Chicago secondary
- Employee range:
  - ideal 50–300
  - acceptable 30–500
  - excluded below 20
- Revenue range:
  - $1M–$50M
- Company stage:
  - growing
  - scaling
  - funded
  - expanding
- Technology profile:
  - CRM
  - ERP
  - spreadsheets
  - HubSpot
  - Salesforce
  - QuickBooks
  - NetSuite
  - Slack
  - Google Workspace
  - Microsoft 365
  - Zapier
  - Make
- Pain points:
  - manual paperwork
  - repetitive data entry
  - approvals
  - disconnected tools
  - document-heavy workflows
- Buying signals:
  - operations hiring
  - RevOps hiring
  - funding
  - leadership change
  - expansion
  - automation/process improvement job posts
- Buyer committee:
  - CTO
  - COO
  - Founder
  - Head of Operations
  - VP Operations
  - Operations Manager
  - possible blockers: IT, finance, procurement, legal
- Disqualifiers
- Priority segments
- Lead scoring rules
- Ready search recipe
- ICP quality score ideally above 85

---

## 14. Mature Mode — Planned

Mature mode is not implemented yet.

Planned mature mode inputs:

- 3–5 best customer websites
- Existing ICP document
- CRM export
- Won-customer list
- Campaign performance data

Planned mature outputs:

- Data-backed ICP
- Pattern analysis
- Lookalike search rules
- Best-fit account profile
- Recommended segments
- Evidence-based scoring model
- Confidence/evidence summary
- Ready search recipe

---

## 15. Output Structure

A completed ICP session returns:

```json
{
  "session_id": "session-id",
  "status": "completed",
  "mode": "beginner",
  "current_step": 5,
  "question": null,
  "question_key": null,
  "mode_instruction": null,
  "icp_output": {
    "mode": "beginner",
    "icp_name": "Example ICP Name",
    "icp_summary": "Example ICP Summary",
    "icp_data": {},
    "search_recipe": {},
    "icp_quality": {},
    "generation_method": "gemini_structured_output",
    "needs_review": false
  },
  "report_path": "reports/example.docx",
  "report_download_url": "/ai/onboarding/report/session-id"
}
```

---

## 16. Report Generation

Each completed ICP session creates a Word report in:

```text
reports/
```

The report includes:

- Session information
- Mode
- User inputs
- ICP output
- Ready search recipe
- ICP quality review
- Database summary
- Tagged dataset examples
- Client review notes

Download endpoint:

```http
GET /ai/onboarding/report/{session_id}
```

---

## 17. Fine-Tuning / Evaluation Dataset

Each completed session creates a record in `ai_dataset_examples`.

The record stores:

- task type
- input JSON
- output JSON
- tags
- review status
- fine-tuning eligibility
- evaluation eligibility

Fallback outputs are marked as needing review and should not be used for fine-tuning until reviewed and approved.

---

## 18. OpenRouter Provider Notes

The provider class is currently named:

```text
GeminiProvider
```

but internally it calls OpenRouter using:

```env
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AI_CHAT_CHAT_MODEL=google/gemini-2.5-flash
```

The class can later be renamed to `OpenRouterProvider`.

---

## 19. Troubleshooting

### Error: Extra inputs are not permitted

Make sure `app/core/config.py` has:

```python
extra="ignore"
```

inside `SettingsConfigDict`.

### UI still shows old text

Hard refresh:

```text
Ctrl + F5
```

Make sure the UI file is:

```text
app/static/chat.html
```

### Database schema looks old

Delete the SQLite database and restart:

Windows PowerShell:

```powershell
del gtm_ai.db
uvicorn app.main:app --reload
```

### Output keeps using fallback

Check:

- valid `OPENROUTER_API_KEY`
- correct `OPENROUTER_BASE_URL`
- `AI_CHAT_CHAT_MODEL=google/gemini-2.5-flash`
- OpenRouter credits are available
- terminal logs for the specific error

### Reports are not generated

Make sure `.env` contains:

```env
REPORTS_DIR=reports
```

You can also create the folder manually:

```bash
mkdir reports
```

### `/chat` not found

Check that:

- `app/static/chat.html` exists
- `app/main.py` has the `/chat` route

---

## 20. Recommended `.gitignore`

Create `.gitignore`:

```gitignore
.env
venv/
__pycache__/
*.pyc
gtm_ai.db
reports/
.DS_Store
.idea/
.vscode/
```

Do not upload:

- `.env`
- OpenRouter API key
- SQLite database
- generated reports
- virtual environment

---

## 21. Next Development Phases

1. Improve generated output quality
2. Refine frontend UI/UX
3. Add Mature Mode
4. Connect search recipe to GTM smart search
5. Add company enrichment
6. Add lead/contact discovery
7. Integrate email generation pipeline
8. Add review/approval workflow for fine-tuning data
9. Prepare hosted open-source LLM option

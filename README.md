# Patch Impact Analyzer

Scrapes League of Legends patch notes, parses them into structured change data, and serves a Next.js dashboard with patch analytics, entity history, and AI-powered search.

Live patch data updates automatically every Wednesday via GitHub Actions. No manual intervention required after deployment.

---

## What it does

- **Parses patch notes** from Riot's website into typed, scored change records (champion/item/system, buff/nerf/adjustment, stat category, delta values)
- **Scores impact** per entity per patch using weighted categories — cooldowns weigh more than base stats, mechanics more than cost changes
- **Predicts indirect champion impact** from item and system changes by matching gameplay tags (burst, mobility, durability, etc.) against champion profiles
- **Semantic search** over all parsed change lines using pgvector embeddings
- **RAG interface** for natural language queries ("How are burst mages affected this patch?")
- **Auto-scrapes** every Wednesday, detects the next patch version, commits the JSON, and triggers a Render redeploy

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL + pgvector |
| Scraping/parsing | BeautifulSoup4, requests |
| LLM fallback | Gemini, OpenAI, or Ollama (opt-in) |
| Frontend | Next.js (TypeScript) |
| Deployment | Render (monorepo: backend + frontend) |
| Automation | GitHub Actions |

---

## Architecture

```
GitHub Actions (weekly)
  └── scrape_current_patch.py        # detect next patch version, check URL
        └── auto_import_patch.py     # fetch HTML → parse → write JSON
              └── fetch_riot_patch.py        # BeautifulSoup extraction
              └── paste_changes_into_patch.py  # rule-based parser + optional LLM fallback
  └── git commit + push → triggers Render deploy

Render deploy
  └── render-start.sh
        └── alembic upgrade head
        └── bootstrap: ingest any JSON in data/raw/ not yet in DB
        └── uvicorn (FastAPI backend)
        └── next start (frontend)

FastAPI backend
  ├── /patch/*        patch list, detail, changes, distribution, comparison
  ├── /search/semantic   pgvector nearest-neighbor over change embeddings
  └── /rag/explain       retrieval-augmented generation via Gemini
```

Patch data lives in `backend/data/raw/<version>.json` — committed to the repo and auto-ingested on each deploy. The DB is the source of truth at runtime; JSON files are the source of truth for reseeding.

---

## Local setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL with pgvector extension

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `DATABASE_URL`.

For Neon, use the pooled connection string from your Neon dashboard (Neon → your project → Connection Details → Pooled connection):
```
DATABASE_URL=postgresql://neondb_owner:YOUR_PASSWORD@ep-quiet-snow-a8xwokgy-pooler.eastus2.azure.neon.tech/neondb?sslmode=require
```

For local Postgres:
```
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/patchdb
```

Run migrations (creates all tables and enables pgvector):
```powershell
alembic upgrade head
```

Ingest existing patch data:
```powershell
python -m app.ingest --file data/raw/26.6.json
```

Start the API:
```powershell
uvicorn app.main:app --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`. API at `http://localhost:8000`.

---

## Pages

| Route | Description |
|---|---|
| `/` | Patch list |
| `/patch/[version]` | Change list and patch notes for a version |
| `/dashboard` | Volatility, risk score, role distribution |
| `/compare` | Side-by-side patch intelligence |
| `/ai` | Semantic search and RAG interface |
| `/entity/[name]` | Full change history for a champion/item/system |

---

## API reference

### Patch data

```
GET /patch/list
GET /patch/{version}
GET /patch/{version}/changes
GET /patch/{version}/distribution
GET /patch/{version}/summary-report
GET /patch/{version}/predicted-impact
GET /patch/compare/intelligence?base_version=26.5&target_version=26.6
```

`/changes` query params: `entity_type`, `category`, `direction`, `tag`, `entity`, `ability`

Examples:
```
GET /patch/26.6/changes?direction=buff&category=cooldown
GET /patch/26.6/changes?tag=jungle
GET /patch/26.6/changes?entity=Viego
GET /patch/26.6/predicted-impact?top_n=40
```

### AI

```
POST /search/semantic
{ "query": "ADC survivability against assassins", "k": 20 }

POST /rag/explain
{ "query": "How are burst mages affected in recent patches?", "k": 12 }
```

---

## Automated scraping

The GitHub Actions workflow (`.github/workflows/scrape-patch.yml`) runs every Wednesday at 14:00 UTC.

It detects the highest patch version already in `data/raw/`, increments it, and checks whether that patch's notes URL is live. If it is, it scrapes and commits the data, then triggers a Render redeploy via webhook.

To run manually: go to **Actions → Scrape Latest Patch Notes → Run workflow**.

No secrets are required for the scrape itself. To enable the Render deploy trigger, add `RENDER_DEPLOY_HOOK_URL` to your repo secrets (from Render dashboard → Service → Settings → Deploy Hook).

---

## Importing a patch manually

From `backend` with the venv active:

```powershell
# Fetch and parse in one command (recommended)
python scripts/auto_import_patch.py --version 26.6 --replace-entities

# Or use the PowerShell wrapper
.\scripts\import_patch.ps1 -Version 26.6
```

To re-ingest an existing JSON without re-fetching:
```powershell
python -m app.ingest --file data/raw/26.6.json
```

---

## LLM fallback (optional)

The parser is rule-based by default. For lines the rules can't resolve, you can opt in to LLM processing.

**Gemini** (used by the GitHub Action when `GEMINI_API_KEY` is set):
```powershell
$env:LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="your_key"
```

**OpenAI:**
```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_key"
$env:OPENAI_MODEL="gpt-4.1-mini"   # optional
```

**Ollama** (local, free):
```powershell
$env:LLM_PROVIDER="ollama"
ollama serve
ollama pull llama3.1:8b
```

Pass `--use-llm-fallback` to `auto_import_patch.py` or `paste_changes_into_patch.py` to enable it. Use `--llm-max-lines` to cap token usage. Use `--llm-dry-run` to preview without writing.

Ollama → Gemini automatic fallback (runs Gemini if Ollama coverage falls below a threshold):
```powershell
$env:LLM_PROVIDER="ollama"
$env:GEMINI_API_KEY="your_key"
$env:LLM_ENABLE_GEMINI_FALLBACK="true"
$env:LLM_LOW_CONFIDENCE_MIN_COVERAGE="0.45"   # optional
```

---

## Tag taxonomy

Each change includes a normalized `tags` array derived deterministically from `stat_name` and value text:

`mobility` `burst` `waveclear` `sustain` `durability` `cc` `utility` `jungle` `mana` `cooldown`

```json
{
  "stat_name": "Base Cooldown",
  "direction": "buff",
  "tags": ["cooldown"]
}
```

Tags power the champion impact predictor — champions whose profiles overlap with high-pressure tags in a patch get flagged as indirectly impacted.

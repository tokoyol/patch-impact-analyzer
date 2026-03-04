## Patch Ingestion Workflow

Use normalized JSON payloads to ingest real patch data into Postgres.

### 1) Ingest from file

From `backend`:

```powershell
.\venv\Scripts\Activate.ps1
python -m app.ingest --file data/raw/26.4.json
```

### 2) Fetch Riot patch scaffold

This fetches raw notes text and writes a normalized scaffold JSON.
It can also auto-extract typed change lines (`champion`/`item`/`system`) for parsing.

```powershell
.\venv\Scripts\Activate.ps1
python scripts/fetch_riot_patch.py --version 26.4 --changes-out data/raw/26.4.changes.auto.txt
```

### 3) Verify API + frontend

Backend:
```text
GET http://127.0.0.1:8000/patch/list
GET http://127.0.0.1:8000/patch/26.4
GET http://127.0.0.1:8000/patch/26.4/distribution
GET http://127.0.0.1:8000/patch/26.4/summary-report
GET http://127.0.0.1:8000/patch/compare/intelligence?base_version=26.3&target_version=26.4
```

Frontend UI pages (http://127.0.0.1:3000):
- `/patch/26.4`: detailed change-list and notes
- `/dashboard`: overview of volatility, risk, and role distribution
- `/compare`: side-by-side patch intelligence
- `/ai`: RAG and Semantic Search interface
- `/entity/{name}`: detailed entity change history

### 4) One-command import (recommended)

From `backend`:

```powershell
.\venv\Scripts\Activate.ps1
.\scripts\import_patch.ps1 -Version 26.4
```

Notes:
- If `data/raw/<version>.changes.txt` does not exist, this now runs **auto mode**:
  fetch Riot page -> auto extract changes -> parse -> ingest.
- If `data/raw/<version>.changes.txt` exists, it runs legacy/manual parse mode for compatibility.
- To run the auto importer directly:

```powershell
python scripts/auto_import_patch.py --version 26.4 --replace-entities
```

- If your `.changes.txt` already exists and you want to keep an edited JSON scaffold, use:

```powershell
.\scripts\import_patch.ps1 -Version 26.4 -SkipFetch
```

### 5) Tag taxonomy and behavior

Each parsed change now includes a normalized `tags` array (lowercase, deduplicated).
Tags are generated deterministically from `stat_name` and value text:

- `mobility`
- `burst`
- `waveclear`
- `sustain`
- `durability`
- `cc`
- `utility`
- `jungle`
- `mana`
- `cooldown`

Example change payload shape:

```json
{
  "stat_name": "Base Cooldown",
  "direction": "buff",
  "tags": ["cooldown"]
}
```

### 6) Query filtered changes

Use:

```text
GET /patch/{version}/changes
```

Optional query params:
- `entity_type` (`champion` default, or `item`, `system`, `all`)
- `category`
- `direction`
- `tag`
- `entity`
- `ability`

Examples:

```text
GET http://127.0.0.1:8000/patch/26.4/changes?direction=buff&category=cooldown
GET http://127.0.0.1:8000/patch/26.4/changes?entity_type=item
GET http://127.0.0.1:8000/patch/26.4/changes?entity_type=system
GET http://127.0.0.1:8000/patch/26.4/changes?tag=jungle
GET http://127.0.0.1:8000/patch/26.4/changes?entity=Viego
GET http://127.0.0.1:8000/patch/26.4/changes?ability=Q
```

Predicted champion impact from item/system changes:

```text
GET http://127.0.0.1:8000/patch/26.4/predicted-impact
GET http://127.0.0.1:8000/patch/26.4/predicted-impact?top_n=40
```

### 7) Semantic Search & RAG

Search parsed change lines using semantic similarity:

```text
POST http://127.0.0.1:8000/search/semantic
{
  "query": "ADC survivability against assassins",
  "k": 20
}
```

Generate a synthesized RAG explanation for your query:

```text
POST http://127.0.0.1:8000/rag/explain
{
  "query": "How are burst mages affected in recent patches?",
  "k": 12
}
```

### 8) Refresh tags in DB after parser changes

If you update parsing/tag rules, re-parse and re-ingest to refresh stored tags:

```powershell
.\venv\Scripts\Activate.ps1
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.4.json --input-file data/raw/26.4.changes.txt --replace-entities
python -m app.ingest --file data/raw/26.4.json
```

### 9) Optional AI fallback for ambiguous lines

The parser is still rule-based by default. AI fallback is opt-in and only runs on unresolved lines.

Provider selection (defaults to Ollama):

```powershell
$env:LLM_PROVIDER="ollama"   # default if omitted
```

#### Ollama (default, local/free)

Install and start Ollama, then pull a model:

```powershell
ollama serve
ollama pull llama3.1:8b
```

Optional Ollama env vars:

```powershell
$env:OLLAMA_BASE_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="llama3.1:8b"
```

Use parser directly with AI fallback (Ollama):```powershell
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.4.json --input-file data/raw/26.4.changes.txt --replace-entities --use-llm-fallback --llm-max-lines 40
python -m app.ingest --file data/raw/26.4.json
```

#### OpenAI (optional hosted provider)

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4.1-mini"   # optional
```

Preview AI suggestions without writing:

```powershell
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.4.json --input-file data/raw/26.4.changes.txt --use-llm-fallback --llm-max-lines 20 --llm-dry-run
```

Use one-command import with AI fallback:

```powershell
.\scripts\import_patch.ps1 -Version 26.4 -SkipFetch -UseLlmFallback -LlmMaxLines 40
```

Notes:
- AI fallback increases latency (and token cost for hosted providers).
- Keep `--llm-max-lines` conservative to control cost.
- Review AI-added changes in `data/raw/<version>.json` before ingesting for production-like runs.

#### Gemini (optional hosted provider)

```powershell
$env:LLM_PROVIDER="gemini"
$env:GEMINI_API_KEY="your_api_key_here"
$env:GEMINI_MODEL="gemini-1.5-flash"   # optional
```

#### Ollama low-confidence -> Gemini automatic fallback

Keep Ollama as primary parser, but enable Gemini backup when Ollama coverage is too low:

```powershell
$env:LLM_PROVIDER="ollama"
$env:GEMINI_API_KEY="your_api_key_here"
$env:LLM_ENABLE_GEMINI_FALLBACK="true"
$env:LLM_LOW_CONFIDENCE_MIN_COVERAGE="0.45"   # optional
```

Behavior:
- Ollama runs first.
- If parsed coverage is below threshold, Gemini is tried automatically.
- The higher-coverage validated result is used.

### 10) Bootstrap and Deployment

The `render-start.sh` script (used in Docker/Render) automatically bootstraps the database with all JSON files found in `backend/data/raw/` that aren't already in the database. 

To force a re-ingest of a specific patch, you can manually run the ingest command:
```powershell
python -m app.ingest --file data/raw/<version>.json
```
or delete the patch from the DB and restart the service.

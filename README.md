## Patch Ingestion Workflow

Use normalized JSON payloads to ingest real patch data into Postgres.

### 1) Ingest from file

From `backend`:

```powershell
.\venv\Scripts\Activate.ps1
python -m app.ingest --file data/raw/14.2.json
```

### 2) Fetch Riot patch scaffold

This fetches raw notes text and writes a normalized scaffold JSON.
It can also auto-extract typed change lines (`champion`/`item`/`system`) for parsing.

```powershell
.\venv\Scripts\Activate.ps1
python scripts/fetch_riot_patch.py --version 14.2 --changes-out data/raw/14.2.changes.auto.txt
```

### 3) Verify API + frontend

```text
GET http://127.0.0.1:8000/patch/14.2
GET http://127.0.0.1:8000/patch/14.2/distribution
http://127.0.0.1:3000/patch/14.2
```

### 4) One-command import (recommended)

From `backend`:

```powershell
.\venv\Scripts\Activate.ps1
.\scripts\import_patch.ps1 -Version 26.2
```

Notes:
- If `data/raw/<version>.changes.txt` does not exist, this now runs **auto mode**:
  fetch Riot page -> auto extract changes -> parse -> ingest.
- If `data/raw/<version>.changes.txt` exists, it runs legacy/manual parse mode for compatibility.
- To run the auto importer directly:

```powershell
python scripts/auto_import_patch.py --version 26.2 --replace-entities
```

- If your `.changes.txt` already exists and you want to keep an edited JSON scaffold, use:

```powershell
.\scripts\import_patch.ps1 -Version 26.2 -SkipFetch
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
GET http://127.0.0.1:8000/patch/26.1/changes?direction=buff&category=cooldown
GET http://127.0.0.1:8000/patch/26.2/changes?entity_type=item
GET http://127.0.0.1:8000/patch/26.2/changes?entity_type=system
GET http://127.0.0.1:8000/patch/26.1/changes?tag=jungle
GET http://127.0.0.1:8000/patch/26.2/changes?entity=Viego
GET http://127.0.0.1:8000/patch/26.1/changes?ability=Q
```

Predicted champion impact from item/system changes:

```text
GET http://127.0.0.1:8000/patch/26.2/predicted-impact
GET http://127.0.0.1:8000/patch/26.2/predicted-impact?top_n=40
```

### 7) Refresh tags in DB after parser changes

If you update parsing/tag rules, re-parse and re-ingest to refresh stored tags:

```powershell
.\venv\Scripts\Activate.ps1
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.1.json --input-file data/raw/26.1.changes.txt --replace-entities
python -m app.ingest --file data/raw/26.1.json
```

### 8) Optional AI fallback for ambiguous lines

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
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.3.json --input-file data/raw/26.3.changes.txt --replace-entities --use-llm-fallback --llm-max-lines 40
python -m app.ingest --file data/raw/26.3.json
```

#### OpenAI (optional hosted provider)

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="your_api_key_here"
$env:OPENAI_MODEL="gpt-4.1-mini"   # optional
```

Preview AI suggestions without writing:

```powershell
python scripts/paste_changes_into_patch.py --patch-json data/raw/26.3.json --input-file data/raw/26.3.changes.txt --use-llm-fallback --llm-max-lines 20 --llm-dry-run
```

Use one-command import with AI fallback:

```powershell
.\scripts\import_patch.ps1 -Version 26.3 -SkipFetch -UseLlmFallback -LlmMaxLines 40
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

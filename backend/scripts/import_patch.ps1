param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$PatchJson,

    [string]$ChangesTxt,

    [switch]$SkipFetch,

    [switch]$UseLlmFallback,

    [int]$LlmMaxLines = 40,

    [switch]$SkipIngest
)

$ErrorActionPreference = "Stop"
$pythonExe = if (Test-Path ".\venv\Scripts\python.exe") { ".\venv\Scripts\python.exe" } else { "python" }

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,

        [Parameter(Mandatory = $true)]
        [string]$FailureMessage
    )

    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw $FailureMessage
    }
}

if (-not $PatchJson) {
    $PatchJson = "data/raw/$Version.json"
}

if (-not $ChangesTxt) {
    $ChangesTxt = "data/raw/$Version.changes.txt"
}

Write-Host "Importing patch $Version"
Write-Host "Patch JSON: $PatchJson"
Write-Host "Changes TXT: $ChangesTxt"

if (Test-Path $ChangesTxt) {
    Write-Host "`nDetected manual changes file. Running legacy pipeline..."
    if (-not $SkipFetch) {
        Invoke-Checked "$pythonExe scripts/fetch_riot_patch.py --version $Version --out $PatchJson" "Fetch scaffold failed."
    }
    else {
        Write-Host "Skipped scaffold fetch (--SkipFetch)."
    }

    $parseCommand = "$pythonExe scripts/paste_changes_into_patch.py --patch-json $PatchJson --input-file $ChangesTxt --replace-entities"
    if ($UseLlmFallback) {
        $parseCommand += " --use-llm-fallback --llm-max-lines $LlmMaxLines"
    }
    Invoke-Checked $parseCommand "Parsing raw changes failed."

    if (-not $SkipIngest) {
        Invoke-Checked "$pythonExe -m app.ingest --file $PatchJson" "Patch ingest failed."
    }
}
else {
    Write-Host "`nNo manual changes file found. Running auto-scrape pipeline..."
    $autoCommand = "$pythonExe scripts/auto_import_patch.py --version $Version --patch-json $PatchJson --replace-entities"
    if ($UseLlmFallback) {
        $autoCommand += " --use-llm-fallback --llm-max-lines $LlmMaxLines"
    }
    if ($SkipIngest) {
        $autoCommand += " --skip-ingest"
    }
    Invoke-Checked $autoCommand "Auto patch import failed."
}

Write-Host "`nDone. Open:"
Write-Host "  http://127.0.0.1:3000/patch/$Version"
Write-Host "  http://127.0.0.1:8000/patch/$Version"
Write-Host "  http://127.0.0.1:8000/patch/$Version/distribution"


<#
.SYNOPSIS
  Deploy (or update) an HTML game to Firebase Storage and register it in
  Firestore's html_games collection.

.DESCRIPTION
  1. Uploads the game HTML to gs://inzone-html/<slug>.html
  2. Uploads the game icon  to gs://inzone-html/<slug>-icon.<ext>
  3. Generates Firebase Storage download tokens for both
  4. Writes / merges the html_games Firestore document via a tiny Python helper
     (reuses the backend's firebase_admin credentials)

.PARAMETER GameHtmlPath
  Absolute path to the .html game file.

.PARAMETER IconPath
  Absolute path to the game icon (jpg/png). Optional on update.

.PARAMETER GameName
  Human-readable game title, e.g. "Tap Targets".

.PARAMETER Description
  One-line description shown in the app store.

.PARAMETER UploaderId
  Firebase UID of the uploading developer.

.PARAMETER GameSlug
  URL-safe slug used as the document ID and storage filename.
  Auto-derived from GameName when omitted.

.PARAMETER Update
  If set, removes the previous storage objects before re-uploading.

.EXAMPLE
  .\deploy_game.ps1 `
      -GameHtmlPath "C:\Users\MAJsh\Downloads\inzone\inzone-flutter-app\assets\html\social_loop_tap_targets.html" `
      -IconPath     "C:\Users\MAJsh\Downloads\inzone\inzone-flutter-app\assets\images\logo.jpg" `
      -GameName     "Tap Targets" `
      -Description  "Tap the targets to get a higher score" `
      -UploaderId   "studio-portal"

.EXAMPLE
  # Update an existing game (removes old files first)
  .\deploy_game.ps1 `
      -GameHtmlPath "C:\path\to\updated_game.html" `
      -GameName     "Tap Targets" `
      -Update
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path $_ })]
    [string]$GameHtmlPath,

    [string]$IconPath,

    [Parameter(Mandatory)]
    [string]$GameName,

    [string]$Description = "",

    [string]$UploaderId = "studio-portal",

    [string]$GameSlug,

    [switch]$Update
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Derive slug ──────────────────────────────────────────────────
if (-not $GameSlug) {
    $GameSlug = ($GameName -replace '[^a-zA-Z0-9]+', '-').ToLower().Trim('-')
}

$Bucket      = "inzone-html"
$HtmlObject  = "$GameSlug.html"
$IconExt     = if ($IconPath) { [System.IO.Path]::GetExtension($IconPath) } else { ".jpg" }
$IconObject  = "$GameSlug-icon$IconExt"

Write-Host "`n=== InZone Game Deploy ===" -ForegroundColor Cyan
Write-Host "  Game:   $GameName ($GameSlug)"
Write-Host "  Bucket: gs://$Bucket"
Write-Host "  Mode:   $(if ($Update) { 'UPDATE' } else { 'NEW' })`n"

# ── Step 1 — Remove old objects (update only) ───────────────────
if ($Update) {
    Write-Host "[1/5] Removing previous objects..." -ForegroundColor Yellow
    gcloud storage rm "gs://$Bucket/$HtmlObject" 2>$null
    if ($IconPath) {
        gcloud storage rm "gs://$Bucket/$IconObject" 2>$null
    }
    Write-Host "      Done.`n"
} else {
    Write-Host "[1/5] New upload — skipping removal.`n" -ForegroundColor DarkGray
}

# ── Step 2 — Upload HTML ────────────────────────────────────────
Write-Host "[2/5] Uploading game HTML..." -ForegroundColor Cyan
gcloud storage cp --content-type=text/html $GameHtmlPath "gs://$Bucket/$HtmlObject"

# ── Step 3 — Token + URL for HTML ───────────────────────────────
Write-Host "[3/5] Setting download token for HTML..." -ForegroundColor Cyan
$HtmlToken = [guid]::NewGuid().ToString()
gcloud storage objects update `
    --update-custom-metadata="firebaseStorageDownloadTokens=$HtmlToken" `
    "gs://$Bucket/$HtmlObject"

$GameUrl = "https://firebasestorage.googleapis.com/v0/b/$Bucket/o/$($HtmlObject)?alt=media&token=$HtmlToken"
Write-Host "      $GameUrl`n" -ForegroundColor Green

# ── Step 4 — Upload icon + token ────────────────────────────────
$IconUrl = ""
if ($IconPath -and (Test-Path $IconPath)) {
    Write-Host "[4/5] Uploading game icon..." -ForegroundColor Cyan
    gcloud storage cp $IconPath "gs://$Bucket/$IconObject"

    $IconToken = [guid]::NewGuid().ToString()
    gcloud storage objects update `
        --update-custom-metadata="firebaseStorageDownloadTokens=$IconToken" `
        "gs://$Bucket/$IconObject"

    $IconUrl = "https://firebasestorage.googleapis.com/v0/b/$Bucket/o/$($IconObject)?alt=media&token=$IconToken"
    Write-Host "      $IconUrl`n" -ForegroundColor Green
} else {
    Write-Host "[4/5] No icon provided — skipping.`n" -ForegroundColor DarkGray
}

# ── Step 5 — Write Firestore html_games document ────────────────
Write-Host "[5/5] Writing to Firestore html_games/$GameSlug ..." -ForegroundColor Cyan

# Build a small inline Python script that reuses the backend's firebase_admin
# credentials (expects GOOGLE_APPLICATION_CREDENTIALS or key.json in cwd).
$PyScript = @"
import sys, os, json
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    print("ERROR: firebase_admin not installed. Run: pip install firebase-admin", file=sys.stderr)
    sys.exit(1)

# Initialise only if not already done
try:
    firebase_admin.get_app()
except ValueError:
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "key.json")
    if not os.path.isabs(cred_path):
        cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), cred_path)
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

doc = {
    "name":        sys.argv[1],
    "description": sys.argv[2],
    "gameUrl":     sys.argv[3],
    "iconUrl":     sys.argv[4],
    "uploaderId":  sys.argv[5],
    "status":      "approved",
}

slug = sys.argv[6]
is_update = sys.argv[7] == "1"

if is_update:
    doc["updatedAt"] = firestore.SERVER_TIMESTAMP
else:
    doc["createdAt"] = firestore.SERVER_TIMESTAMP

db.collection("html_games").document(slug).set(doc, merge=True)
print(f"OK  html_games/{slug}")
"@

$TempPy = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.py'
$PyScript | Out-File -Encoding utf8 $TempPy

try {
    python $TempPy $GameName $Description $GameUrl $IconUrl $UploaderId $GameSlug $(if ($Update) {"1"} else {"0"})
} finally {
    Remove-Item $TempPy -ErrorAction SilentlyContinue
}

Write-Host "`n=== Deploy complete ===" -ForegroundColor Green
Write-Host "  gameUrl : $GameUrl"
Write-Host "  iconUrl : $IconUrl"
Write-Host "  doc     : html_games/$GameSlug`n"

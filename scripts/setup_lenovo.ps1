<#
  RUN ON: the Lenovo LOQ (target machine), from the extracted project folder.
  Creates .venv, installs dependencies, then runs the environment check.
  Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup_lenovo.ps1
          add -WithDev to also install pytest (to run the test-suite on the Lenovo).
  Nothing is installed system-wide; everything goes into the project's .venv folder.
#>
param([switch]$WithDev)

$ErrorActionPreference = "Continue"  # pip/py write warnings to stderr; exit codes are checked explicitly below
Set-Location (Split-Path $PSScriptRoot -Parent)

function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# --- 1. find a suitable Python (3.12 preferred, 3.10-3.13 accepted) ---------------
$pyExe = $null; $pyArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in "3.12", "3.13", "3.11", "3.10") {
        $null = & py "-$v" -c "import sys" 2>&1
        if ($LASTEXITCODE -eq 0) { $pyExe = "py"; $pyArgs = @("-$v"); break }
    }
}
if (-not $pyExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($ver -match "^3\.(10|11|12|13)$") { $pyExe = "python" }
}
if (-not $pyExe) {
    Fail "Python 3.12 was not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), or run:  winget install Python.Python.3.12  then re-run this script."
}
Write-Host "Using Python: $pyExe $pyArgs  ->  $(& $pyExe @pyArgs --version)"

# --- 2. virtual environment ------------------------------------------------------
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment (.venv)..."
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Could not create the virtual environment." }
}
$venvPy = ".venv\Scripts\python.exe"

# --- 3. dependencies ---------------------------------------------------------------
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Host "(pip upgrade failed - continuing with the existing pip)" -ForegroundColor Yellow }
$req = if ($WithDev) { "requirements-dev.txt" } else { "requirements.txt" }
Write-Host "Installing $req (this downloads about 100-150 MB the first time)..."
& $venvPy -m pip install -r $req
if ($LASTEXITCODE -ne 0) { Fail "pip install failed. Check your internet connection and read the messages above." }

# --- 4. check ----------------------------------------------------------------------
Write-Host "`nRunning environment check...`n"
& $venvPy -m nova --check

Write-Host "`nNext steps:"
Write-Host "  1. Download the speech model:   .venv\Scripts\python.exe -m nova --download-model whisper-small"
Write-Host "  2. Start NOVA:                  scripts\run_nova.bat"

<#
  RUN ON: the Dell (development laptop).
  Packs the project into dist\nova-<timestamp>.zip for transfer to the Lenovo.
  Leaves out: .venv, .git, caches, models, databases, logs, .env, config.json.
  Usage:  powershell -ExecutionPolicy Bypass -File scripts\export_project.ps1
#>
param([string]$OutDir = "dist")

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outPath = Join-Path $root $OutDir
New-Item -ItemType Directory -Force $outPath | Out-Null
$zipPath = Join-Path $outPath ("nova-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".zip")

$skipDirs  = @(".venv", ".git", "__pycache__", ".pytest_cache", "dist", ".tmp_data", "models")
$skipFiles = @("*.pyc", "*.db", "*.log", ".env", "config.json")

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")
$count = 0
try {
    Get-ChildItem -Path $root -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($root.Length).TrimStart("\", "/")
        $segments = $rel -split "[\\/]"
        if ($segments[0..($segments.Length - 2)] | Where-Object { $skipDirs -contains $_ }) { return }
        foreach ($pattern in $skipFiles) { if ($_.Name -like $pattern) { return } }
        $entryName = "nova/" + ($rel -replace "\\", "/")
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entryName, "Optimal")
        $count++
    }
}
finally { $zip.Dispose() }

$sizeKb = [math]::Round((Get-Item $zipPath).Length / 1KB)
Write-Host "Created $zipPath  ($count files, $sizeKb KB)"
Write-Host "Copy this ZIP to the Lenovo (USB stick, OneDrive, Google Drive...), extract it, then follow docs\DEPLOY_LENOVO.md."

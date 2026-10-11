param(
    [switch]$WithModel,
    [switch]$MainOnly,
    [switch]$BuildWeb,
    [switch]$DryRun,
    [string]$Config
)
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$taskRoot = Split-Path -Parent $PSScriptRoot
$setupArgs = @("run", "--no-project", "--python", "3.12", (Join-Path $PSScriptRoot "setup.py"))
if ($WithModel) { $setupArgs += "--with-model" }
if ($MainOnly) { $setupArgs += "--main-only" }
if ($BuildWeb) { $setupArgs += "--build-web" }
if ($DryRun) { $setupArgs += "--dry-run" }
if ($Config) { $setupArgs += @("--config", (Resolve-Path $Config).Path) }
Push-Location $taskRoot
try {
    & uv @setupArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

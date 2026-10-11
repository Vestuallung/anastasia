param(
    [switch]$MainOnly,
    [switch]$SkipModel,
    [switch]$Plan,
    [string]$DataDir,
    [string]$Config
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
if (!$DataDir) { $DataDir = Join-Path $PSScriptRoot ".runtime" }
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
foreach ($folder in @("cache\uv", "temp", "tools\uv")) {
    New-Item -ItemType Directory -Force (Join-Path $DataDir $folder) | Out-Null
}
if (!$env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $DataDir "cache\uv" }
if (!$env:UV_PYTHON_INSTALL_DIR) { $env:UV_PYTHON_INSTALL_DIR = Join-Path $DataDir "python" }
if (!$env:UV_TOOL_DIR) { $env:UV_TOOL_DIR = Join-Path $DataDir "tools\envs" }
if (!$env:UV_TOOL_BIN_DIR) { $env:UV_TOOL_BIN_DIR = Join-Path $DataDir "tools\bin" }
$env:TEMP = Join-Path $DataDir "temp"
$env:TMP = $env:TEMP
$taskUv = Get-Command uv -ErrorAction SilentlyContinue
if ($taskUv) { $taskUvPath = $taskUv.Source }
else {
    $taskUvPath = Join-Path $DataDir "tools\uv\uv.exe"
    if (!(Test-Path $taskUvPath)) {
        $match = Select-String -Path (Join-Path $PSScriptRoot "installer.toml") -Pattern '^windows_archive = "(.*)"$'
        $url = $match.Matches[0].Groups[1].Value
        $archive = Join-Path $DataDir "temp\uv.zip"
        for ($attempt=1; $attempt -le 3; $attempt++) {
            try { Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $archive -TimeoutSec 120; break }
            catch { if ($attempt -eq 3) { throw }; Start-Sleep -Seconds 2 }
        }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $DataDir "tools\uv") -Force
    }
}
$env:KARAOKE_UV = $taskUvPath
$taskArgs = @("run", "--no-project", "--python", "3.12", (Join-Path $PSScriptRoot "scripts\bootstrap.py"), "--data-dir", $DataDir)
if ($MainOnly) { $taskArgs += "--main-only" }
if ($SkipModel) { $taskArgs += "--skip-model" }
if ($Plan) { $taskArgs += "--plan" }
if ($Config) { $taskArgs += @("--config", (Resolve-Path $Config).Path) }
& $taskUvPath @taskArgs
exit $LASTEXITCODE

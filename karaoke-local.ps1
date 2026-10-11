$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:KARAOKE_HOME = $PSScriptRoot
$taskEnvironment = Join-Path $PSScriptRoot ".runtime\environment.ps1"
if (Test-Path $taskEnvironment) { . $taskEnvironment }
$taskUv = if ($env:KARAOKE_UV) { $env:KARAOKE_UV } else { "uv" }
& $taskUv run --project $PSScriptRoot karaoke @args
exit $LASTEXITCODE

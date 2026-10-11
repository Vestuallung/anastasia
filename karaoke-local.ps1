$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:KARAOKE_HOME = $PSScriptRoot
uv run --project $PSScriptRoot karaoke @args
exit $LASTEXITCODE

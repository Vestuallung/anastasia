$env:KARAOKE_HOME = $PSScriptRoot
uv run --project $PSScriptRoot karaoke @args
exit $LASTEXITCODE

$ErrorActionPreference = "Stop"
python (Join-Path $PSScriptRoot "../build.py") tracker @args
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

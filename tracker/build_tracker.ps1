$source = $PSScriptRoot
$stagingRoot = Join-Path $env:TEMP ("sticker-star-build-" + [guid]::NewGuid().ToString())
$staging = Join-Path $stagingRoot (Split-Path -Leaf $source)

New-Item -ItemType Directory -Path $staging -Force | Out-Null
robocopy $source $staging /E /XD .git .github .vscode __pycache__ lua_definition tools randomizer /XF .gitignore build_tracker.ps1 build.ps1 make_hash.py *.kra archive.py .luarc.json | Out-Null

if ($LASTEXITCODE -ge 8) {
	throw "Failed to stage pack contents."
}

py .\archive.py -Path $staging -DestinationPath ..\generated\sticker-star-poptracker.zip -Force
Remove-Item $stagingRoot -Recurse -Force

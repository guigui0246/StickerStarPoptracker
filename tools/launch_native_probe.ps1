param(
    [Parameter(Mandatory = $true)][string]$ProfilePath,
    [Parameter(Mandatory = $true)][string]$RomPath,
    [string]$MoviePath = 'dist/native-long-startup-input.ctm',
    [string]$RecordingPath
)

$ErrorActionPreference = 'Stop'
# The Windows Python launcher can leave its child alive after the terminal is
# interrupted. An earlier observer must not query the newly started RPC server
# before guest memory exists, because this emulator build crashes on that read.
$activeObservers = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'tools[/\\]test_native_(thing|peel|ski)_probe\.py' }
if ($activeObservers) {
    throw 'Stop previous native Thing/peel/ski observers and their Python child processes before restarting the emulator.'
}
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$validationPath = [IO.Path]::GetFullPath((Join-Path $workspacePath '.validation'))
$resolvedProfile = (Resolve-Path -LiteralPath $ProfilePath).Path
if (-not $resolvedProfile.StartsWith($validationPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Native probes must use a disposable profile inside this workspace .validation directory.'
}
$executablePath = Join-Path $resolvedProfile 'citra.exe'
$configPath = Join-Path $resolvedProfile 'user/config/sdl2-config.ini'
$resolvedRom = (Resolve-Path -LiteralPath $RomPath).Path
$resolvedMovie = (Resolve-Path -LiteralPath $MoviePath).Path
$probeSettings = Get-Content -LiteralPath $configPath -Raw
foreach ($settingName in @('volume', 'output_type')) {
    if ([regex]::Matches($probeSettings, "(?m)^[ \t]*$settingName[ \t]*=.*$").Count -ne 1) {
        throw "Missing or ambiguous audio setting: $settingName"
    }
}
# The null audio backend survives restarts and does not rely on Windows mute.
$probeSettings = [regex]::Replace($probeSettings, '(?m)^[ \t]*volume[ \t]*=.*$', 'volume = 0')
$probeSettings = [regex]::Replace($probeSettings, '(?m)^[ \t]*output_type[ \t]*=.*$', 'output_type = 1')
Set-Content -LiteralPath $configPath -Value $probeSettings
$probeArguments = @(
    ('--movie-play="' + $resolvedMovie + '"'), ('"' + $resolvedRom + '"')
)
if ($RecordingPath) {
    $resolvedRecording = [IO.Path]::GetFullPath((Join-Path $workspacePath $RecordingPath))
    if (-not $resolvedRecording.StartsWith($validationPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
        (Test-Path -LiteralPath $resolvedRecording)) {
        throw 'Recordings must use a new file inside the disposable validation directory.'
    }
    $probeArguments = @(('--dump-video="' + $resolvedRecording + '"')) + $probeArguments
}
$probeProcess = Start-Process -FilePath $executablePath -WorkingDirectory $workspacePath -WindowStyle Hidden -PassThru -ArgumentList $probeArguments
[pscustomobject]@{ ProcessId = $probeProcess.Id; Profile = $resolvedProfile; Audio = 'Disabled' }

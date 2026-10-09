param(
    [Parameter(Mandatory = $true)][string]$ProfilePath,
    [Parameter(Mandatory = $true)][string]$RomPath
)

# Interactive game validation needs a controllable window. Automated probes
# continue using launch_native_probe.ps1 and its hidden window by default.
$ErrorActionPreference = 'Stop'
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$validationPath = [IO.Path]::GetFullPath((Join-Path $workspacePath '.validation'))
$resolvedProfile = (Resolve-Path -LiteralPath $ProfilePath).Path
if (-not $resolvedProfile.StartsWith($validationPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Interactive tests must use an isolated profile inside .validation.'
}
$configPath = Join-Path $resolvedProfile 'user/config/sdl2-config.ini'
$settingsText = Get-Content -LiteralPath $configPath -Raw
foreach ($settingName in @('volume', 'output_type')) {
    if ([regex]::Matches($settingsText, "(?m)^[ \t]*$settingName[ \t]*=.*$").Count -ne 1) {
        throw "Missing or ambiguous audio setting: $settingName"
    }
}
$settingsText = [regex]::Replace($settingsText, '(?m)^[ \t]*volume[ \t]*=.*$', 'volume = 0')
$settingsText = [regex]::Replace($settingsText, '(?m)^[ \t]*output_type[ \t]*=.*$', 'output_type = 1')
# Empty SDL bindings vary between emulator builds. Make the disposable test
# controls explicit while preserving any bindings already configured by a tester.
$interactiveBindings = @{ button_a = 4; button_b = 22; button_x = 29; button_y = 27; button_start = 40; button_up = 82; button_down = 81; button_left = 80; button_right = 79 }
foreach ($binding in $interactiveBindings.GetEnumerator()) {
    $settingsText = [regex]::Replace($settingsText, "(?m)^[ \t]*$($binding.Key)[ \t]*=[ \t\r]*$", "$($binding.Key) = engine:keyboard,code:$($binding.Value)")
}
Set-Content -LiteralPath $configPath -Value $settingsText
$resolvedRom = (Resolve-Path -LiteralPath $RomPath).Path
$testProcess = Start-Process -FilePath (Join-Path $resolvedProfile 'citra.exe') -WorkingDirectory $workspacePath -WindowStyle Normal -PassThru -ArgumentList ('"' + $resolvedRom + '"')
[pscustomobject]@{ ProcessId = $testProcess.Id; Profile = $resolvedProfile; Audio = 'Disabled'; Purpose = 'Interactive game validation' }

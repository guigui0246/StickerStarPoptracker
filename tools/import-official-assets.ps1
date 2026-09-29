$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$gallery = 'https://www.mariowiki.com/Gallery:Paper_Mario:_Sticker_Star'
$htmlPath = Join-Path $root '.asset-gallery.html'
if (!(Test-Path $htmlPath)) { Invoke-WebRequest $gallery -OutFile $htmlPath }
$html = Get-Content $htmlPath -Raw
$images = @{}
function Normalize([string]$value) { return ([System.Net.WebUtility]::HtmlDecode($value).ToLower() -replace '[^a-z0-9]', '') }
foreach ($match in [regex]::Matches($html, '<a href="/File:([^"]+)" class="image" title="([^"]*)"><img[^>]+src="([^"]+)"')) {
    $key = Normalize $match.Groups[2].Value
    $url = $match.Groups[3].Value -replace '/images/thumb/', '/images/' -replace '/\d+px-[^/]+$', ''
    # Later entries are the in-game stickers and scraps, rather than promotional art.
    $images[$key] = @{ url = $url; page = 'https://www.mariowiki.com/File:' + $match.Groups[1].Value }
}
$itemsPath = Join-Path $root 'items/items.json'
$original = Get-Content $itemsPath -Raw
$items = $original | ConvertFrom-Json
$sources = @()
$updated = $original
foreach ($item in $items) {
    $name = $item.name
    if ($item.codes -like 'scrap_*') { $name = $name -replace ' Scrap$', '' }
    if ($item.codes -eq 'paperization') { $name = 'Kersti' }
    if ($item.codes -eq 'museum_kersti_sticker') { $name = 'Kersti' }
    if ($item.codes -eq 'req_thing_battery') { $name = 'D-Cell Battery' }
    $key = Normalize $name
    if (!$images.ContainsKey($key)) { continue }
    $source = $images[$key]
    if ($source.url -notmatch '\.png$') { continue }
    $path = $item.img -replace '\.svg$', '.png'
    $destination = Join-Path $root $path
    try {
        if (!(Test-Path $destination)) { Invoke-WebRequest $source.url -OutFile $destination }
        $bytes = [System.IO.File]::ReadAllBytes($destination)
        if ($bytes.Length -lt 24 -or [BitConverter]::ToString($bytes[0..7]) -ne '89-50-4E-47-0D-0A-1A-0A') { throw "Invalid PNG: $path" }
        $updated = $updated.Replace($item.img, $path)
        $sources += [pscustomobject]@{ asset = $path; name = $item.name; source_page = $source.page; source_image = $source.url }
    } catch { Write-Warning "$name : $_" }
}
[System.IO.File]::WriteAllText($itemsPath, $updated)
$sources | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $root 'images/official-assets.json') -Encoding utf8
Write-Output "Replaced $($sources.Count) item images."

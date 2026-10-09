"""Asset-free, catalog-specific PopTracker packs with schematic region maps."""

from collections import Counter
from html import escape
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .tracker_catalog import TrackerCatalog, lua_string

CHECKS_PER_PAGE = 16


def svg(width: int, height: int, content: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
        f'<rect width="{width}" height="{height}" fill="#192631"/>{content}</svg>'
    )


def tracking_script(catalog: TrackerCatalog) -> str:
    """Use only this pack's mappings; checks never grant received items."""
    fixed = catalog.game.fixed_rewards
    lines = ["local items, locations, seen, counts = {}, {}, {}, {}"]
    for item in catalog.game.items:
        if item.id not in set(fixed.values()):
            lines.append(f"items[{catalog.registry.items[item.id]}] = {lua_string(catalog.item_code(item.id))}")
    for location in catalog.game.locations:
        if location.id not in fixed:
            code = lua_string(catalog.location_code(location.id))
            lines.append(f"locations[{catalog.registry.locations[location.id]}] = {code}")
    lines.append("local starting = {}")
    for item, count in Counter(catalog.game.starting_items).items():
        lines.append(f"starting[{lua_string(catalog.item_code(item))}] = {count}")
    lines.append("local expected_settings = nil")
    if catalog.settings is not None:
        settings = catalog.settings.to_json()
        lines.append(
            "expected_settings = {album_pages=" + lua_string(settings["album_pages"])
            + ", banners=" + lua_string(settings["banners"]) + "}"
        )
    lines.append(
        """local bound = false
local function reset(slot)
    bound = false
    seen, counts = {}, {}
    for _, code in pairs(items) do
        local object = Tracker:FindObjectForCode(code)
        if object then object.AcquiredCount = starting[code] or 0 end
    end
    for _, code in pairs(locations) do
        local object = Tracker:FindObjectForCode(code)
        if object then object.AvailableChestCount = object.ChestCount end
    end
    if type(slot) ~= "table" or slot.catalog_hash ~= TRACKER_CATALOG_HASH then
        print("Sticker Star tracker requires the matching catalog.")
        return
    end
    local mapping = slot.tracker
    if type(mapping) ~= "table" or mapping.format_version ~= 1
        or mapping.catalog_hash ~= TRACKER_CATALOG_HASH
        or type(mapping.items) ~= "table" or type(mapping.locations) ~= "table" then return end
    if expected_settings then
        if type(mapping.settings) ~= "table" then return end
        for key, value in pairs(expected_settings) do
            if mapping.settings[key] ~= value then return end
        end
    end
    for id, code in pairs(items) do
        local item = mapping.items[tostring(id)] or mapping.items[id]
        if type(item) ~= "table" or item.code ~= code or item.type ~= "consumable" then return end
    end
    for id, code in pairs(locations) do
        if (mapping.locations[tostring(id)] or mapping.locations[id]) ~= code then return end
    end
    for id, item in pairs(mapping.items) do
        if type(item) ~= "table" or not items[tonumber(id)] or items[tonumber(id)] ~= item.code then return end
    end
    for id, code in pairs(mapping.locations) do
        if locations[tonumber(id)] ~= code then return end
    end
    bound = true
    for _, id in ipairs(Archipelago.CheckedLocations or {}) do
        local code = locations[id]
        local object = code and Tracker:FindObjectForCode(code)
        if object then object.AvailableChestCount = 0 end
    end
end
local function receive(index, id)
    if not bound or seen[index] then return end
    seen[index] = true
    local code = items[id]
    if not code then return end
    counts[code] = (counts[code] or 0) + 1
    local object = Tracker:FindObjectForCode(code)
    if object then object.AcquiredCount = math.min(object.MaxCount, math.max(starting[code] or 0, counts[code])) end
end
local function checked(id)
    if not bound then return end
    local code = locations[id]
    local object = code and Tracker:FindObjectForCode(code)
    if object then object.AvailableChestCount = 0 end
end
if Archipelago then
    Archipelago:AddClearHandler("Sticker Star catalog", reset)
    Archipelago:AddItemHandler("Sticker Star inventory", receive)
    Archipelago:AddLocationHandler("Sticker Star checks", checked)
end
"""
    )
    return "\n".join(lines)


def pack_files(catalog: TrackerCatalog) -> dict[str, str]:
    """Build file contents in memory; do not invent geographic coordinates."""
    files: dict[str, str] = {}
    fixed = catalog.game.fixed_rewards
    starters = Counter(catalog.game.starting_items)
    items = []
    for item in catalog.game.items:
        if item.id in set(fixed.values()):
            continue
        code = catalog.item_code(item.id)
        image = f"images/{code}.svg"
        initials = "".join(word[0] for word in item.name.split()[:3])
        files[image] = svg(
            64, 64,
            '<rect x="3" y="3" width="58" height="58" rx="10" fill="#355168"/>'
            f'<text x="32" y="39" text-anchor="middle" font-size="20" fill="#fff">{escape(initials)}</text>',
        )
        items.append({
            "name": item.name, "type": "consumable", "codes": code, "img": image,
            "max_quantity": max(9999, starters[item.id], catalog.game.pool.count(item.id)),
            "initial_quantity": starters[item.id],
        })
    locations = []
    maps = []
    tabs = []
    for index, region in enumerate(catalog.game.regions):
        checks = [
            location for location in catalog.game.locations if location.region_id == region.id and location.id not in fixed
        ]
        if not checks:
            continue
        pages = []
        for offset in range(0, len(checks), CHECKS_PER_PAGE):
            page = checks[offset:offset + CHECKS_PER_PAGE]
            map_name = f"region_{index}" + (f"_{offset // CHECKS_PER_PAGE + 1}" if len(checks) > CHECKS_PER_PAGE else "")
            image = f"images/{map_name}.svg"
            content = f'<text x="20" y="30" font-size="20" fill="#fff">{escape(region.name)}</text>'
            content += '<text x="20" y="54" font-size="12" fill="#b8c9d7">Schematic check list</text>'
            for row, location in enumerate(page):
                y = 85 + row * 32
                content += f'<text x="48" y="{y + 5}" font-size="14" fill="#fff">{escape(location.name)}</text>'
                locations.append({
                    "name": f"ss_location_{catalog.registry.locations[location.id]}",
                    "map_locations": [{"map": map_name, "x": 24, "y": y}],
                    "sections": [{
                        "name": "Check", "item_count": 1,
                        "access_rules": ["$" + catalog.access_function(location.id)],
                    }],
                })
            files[image] = svg(760, 100 + len(page) * 32, content)
            maps.append({"name": map_name, "img": image, "location_size": 18})
            pages.append({
                "title": f"{offset + 1}–{offset + len(page)}", "content": {"type": "map", "maps": [map_name]},
            })
        content_layout = pages[0]["content"] if len(pages) == 1 else {"type": "tabbed", "tabs": pages}
        tabs.append({"title": region.name, "content": content_layout})
    codes = [catalog.item_code(item.id) for item in catalog.game.items if item.id not in set(fixed.values())]
    layout_tabs: list[dict[str, object]] = [
        {"title": "Checks", "content": {"type": "tabbed", "tabs": tabs} if tabs else {
            "type": "text", "text": "No randomized checks",
        }},
        {"title": "Received items", "content": {
            "type": "itemgrid", "item_size": 48, "rows": [codes[index:index + 10] for index in range(0, len(codes), 10)],
        }},
    ]
    if catalog.settings is not None:
        album = {
            "all_at_start": "All eight pages at start",
            "randomized": "Two base pages and six shuffled upgrades",
        }[catalog.settings.album_pages.value]
        banners = {"original": "Original thresholds", "reduced": "One tenth, rounded up", "off": "Disabled"}[
            catalog.settings.banners.value
        ]
        layout_tabs.append({"title": "Configuration", "content": {
            "type": "text", "text": f"Album: {album}\nBanners: {banners}\nItem counters show received totals.",
        }})
    layout = {"tracker_default": {"type": "tabbed", "tabs": layout_tabs}}
    variant_hash = hashlib.sha256(json.dumps({
        "mappings": catalog.mappings(), "starting_items": catalog.game.starting_items,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
    manifest = {
        "name": "Sticker Star catalog tracker", "game_name": "Paper Mario: Sticker Star",
        "package_version": "1.0.0", "package_uid": "sticker_star_catalog_" + catalog.catalog_hash + "_" + variant_hash,
        "author": "Sticker Star tools", "min_poptracker_version": "0.25.2",
        "variants": {"default": {"display_name": "Catalog tracker", "flags": ["ap"]}},
    }
    for name, value in (
        ("manifest.json", manifest), ("items/items.json", items), ("locations/locations.json", locations),
        ("maps/maps.json", maps), ("layouts/layouts.json", layout), ("tracker-data.json", catalog.data_package()),
    ):
        files[name] = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    files["scripts/catalog.lua"] = catalog.lua()
    files["scripts/autotracking.lua"] = tracking_script(catalog)
    files["scripts/init.lua"] = (
        'Tracker:AddItems("items/items.json")\nScriptHost:LoadScript("scripts/catalog.lua")\n'
        'Tracker:AddMaps("maps/maps.json")\nTracker:AddLocations("locations/locations.json")\n'
        'Tracker:AddLayouts("layouts/layouts.json")\nScriptHost:LoadScript("scripts/autotracking.lua")\n'
    )
    return files


def write_tracker_pack(catalog: TrackerCatalog, output: Path) -> None:
    """Only generation commands call this; preserve any existing pack."""
    files = pack_files(catalog)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr("sticker-star/" + name, content)

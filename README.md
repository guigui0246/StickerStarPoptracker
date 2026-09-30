# StickerStarPoptracker

A PopTracker package scaffold for **Paper Mario: Sticker Star** with:

- an original SVG world map and SVG level maps for every stage, with multi-section splits for more complex routes,
- an **Items** tab for abilities, level clears, major paperization objects, and boss tools,
- a **Museum** tab that lets you check every sticker exhibit one by one,
- location logic notes for mini stars / Royal Stickers, special objects, and major required stickers or Things.

## Manual randomizer tracking

- **Received Stars / Royals** tracks rewards received from any shuffled check.
  A received exit star opens its destination; checking off its source location
  does not grant the star. Alternate exits have separate items.
- **Boss Unlocks** tracks boss access independently of Royal Sticker ownership.
  Recommended boss weakness stickers no longer act as mandatory boss gates.
- **Sticker Unlocks** tracks generic shop unlocks and Thing-shop unlocks. These
  items are separate from the museum's donation checkboxes.
- **Door Places** has one independent received unlock per numbered level, grouped
  into W1–W6. Door use needs Paperization, the Secret Door sticker, and that
  level's unlock. Having another level's door unlock does not satisfy the rule.
- **Decalburg** and **Surfshine Harbor** have their own map tabs and world-map
  markers. Town checks include the shop conversations, Fountain, Warehouse Door,
  Vacuum, Ship's Wheel, and Big Cheep Cheep. Their received tools are in
  **Town Tools**. Town diagrams are tracker overviews rather than game maps.
- **Entrance Overrides** marks entrances you have opened when their exact gate
  is not yet reconstructed. World 1-1 and 3-1 start accessible; other world
  entrances do not require an invented chain of Royal Stickers.
- A map check represents a shuffled reward pickup. The item rewarded there
  must be marked separately in Items. This package has no emulator connection.
- The map catalog still contains representative checks rather than every game
  event. Enemy types, Kamek fights, banners, all shops, Wiggler
  events, and some puzzle prerequisites need complete event catalogs before
  this tracker can claim complete randomizer reachability. Entrance overrides
  provide manual control meanwhile. All 38 numbered levels have door-place items;
  only existing door-related checks have their door requirements applied so far.
- Old Stage Clear toggles were retired rather than reinterpreting old save flags
  as received stars. Re-enter your received progression items when updating.

Tracker predicates live in `scripts/randomizer_logic.json`; regenerate their
Lua with `tools/render_tracker_logic.py`. Regression checks are in
`tools/test_tracker_logic.py` and `tools/validate_logic.py`.

The emulator patch is deferred until a new game dump is available. Its checklist
is [randomizer/PATCH_TODO.md](randomizer/PATCH_TODO.md). The separate Python seed
prototype is not a playable patch and is not bundled in the tracker pack.

## Repository layout

- `manifest.json` – PopTracker package metadata
- `scripts/` – loads items, layouts, logic, maps, and locations
- `items/items.json` – tracker items and museum checkboxes
- `layouts/` – root tabs plus item-grid layouts
- `maps/maps.json` – world / level map registration
- `locations/` – world map and per-stage map markers
- `images/maps/*.png` – bundled map art used by the tracker (SVG sources are retained)

## Notes

- Item icons use original **Paper Mario: Sticker Star** artwork and game sprites where matching images are available, sourced from the [Super Mario Wiki gallery](https://www.mariowiki.com/Gallery:Paper_Mario:_Sticker_Star). Nintendo / Intelligent Systems retain ownership of this artwork; it is not covered by any repository code license. Per-image source links are recorded in `images/official-assets.json`.
- Custom fallbacks remain for unmatched items and the maps, rendered as PNG because PopTracker does not load SVG images. The map artwork is tailored to the tracker’s location coordinates, so screenshots cannot be substituted without remapping the markers.
- To refresh available official icons, run `tools/import-official-assets.ps1` with PowerShell. It checks downloaded PNG signatures and only changes references for successfully downloaded images.
- The tracker now splits several multi-route stages into separate map sections so route checks are easier to read.
- The tracker focuses on major progression: stage clears, mini stars / Royal Stickers, special paperization objects, and required boss tools.

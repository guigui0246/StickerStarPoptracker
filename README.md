# StickerStarPoptracker

A PopTracker package scaffold for **Paper Mario: Sticker Star** with:

- an original SVG world map and SVG level maps for every stage, with multi-section splits for more complex routes,
- an **Items** tab for abilities, level clears, major paperization objects, and boss tools,
- a **Museum** tab that lets you check every sticker exhibit one by one,
- location logic notes for mini stars / Royal Stickers, special objects, and major required stickers or Things.

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

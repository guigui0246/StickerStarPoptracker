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
- `images/maps/*.svg` – bundled fallback map art used by the tracker

## Notes

- This repository currently ships **redistributable fallback SVG art** instead of bundling Nintendo-owned images. If licensed or first-party assets are provided later, they can replace these tracker assets privately without changing the tracker data files.
- The tracker now splits several multi-route stages into separate map sections so route checks are easier to read.
- The tracker focuses on major progression: stage clears, mini stars / Royal Stickers, special paperization objects, and required boss tools.

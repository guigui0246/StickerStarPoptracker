# StickerStarPoptracker

A PopTracker package scaffold for **Paper Mario: Sticker Star** with:

- an original SVG world map and SVG level maps for every stage,
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
- `images/maps/*.svg` – original SVG art used by the tracker

## Notes

- The issue requested official world-map art. This repository intentionally uses an **original SVG world map** instead, so the pack can be redistributed without bundling Nintendo-owned artwork.
- The tracker focuses on major progression: stage clears, mini stars / Royal Stickers, special paperization objects, and required boss tools.

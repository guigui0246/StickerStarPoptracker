# Typed Sticker Star randomizer

The typed generation engine works without external packages. The Archipelago
adapter targets 0.6.8. Both use the same `GameDefinition`, rules, regions, and
fixed rewards. The bundled catalog is explicitly a **logic demonstration**,
not a complete Sticker Star randomizer. An experimental combat-sticker ROM
override and a Citra memory transport are now implemented. The full progression
patch and Archipelago runtime delivery remain unfinished.

## Structure

- `domain/items.py`: immutable `Item` and fixed `Event` rewards.
- `domain/locations.py`: `Location`, fixed `Goal`, victory `EndGoal`.
- `domain/regions.py`: `Region`, sole `StartingRegion`, directional `Vector`, two-way `Path`.
- `domain/rules.py`: composable `Rules` and a typed inventory interface.
- `domain/world.py`: validated registries, exact pool size, references, and fixed rewards.
- `standalone/`: graph traversal, fill, sphere verification, command-line interface.
- `data/`: example catalog and strict version-2 JSON loader.
- `integrations/archipelago/`: native AP world, items, checks, entrances, slot output.
- `integrations/rom/`: read-only decrypted ExeFS/RomFS file inventory.
- `integrations/rom/kdm.py`: lossless typed KDM views and checked pointer edits.
- `integrations/rom/pickups.py`: 964 item records mapped to 227 real game rooms.
- `integrations/rom/ksm.py`: lossless typed constants, imports, and save-variable references.
- `integrations/rom/sticker_patch.py`: experimental combat-sticker overrides.
- `integrations/citra/`: typed UDP memory transport for Citra build `608383e`.
- `legacy/`: original version-1 JSON/reward code; `core.py` preserves existing imports.
- `tests/`: graph and generator regression tests.

Regions group locations through `Location.region_id`; paths reference region IDs.
This avoids circular mutable ownership. A region can have any number of paths,
including parallel paths. Only the starting region is inherently reachable;
other regions require traversal from it. Open paths may make other regions
reachable immediately. The example starts at `Menu`, with Decalburg behind
`Decalburg Access`. Return paths have independent rules.

Events attach to one check using `Event.location_id`. Goals attach to their
specific item. Both are excluded from randomized placements. The generator
collects them as their regions and rules become reachable. Winning requires
collecting the EndGoal at its actual reachable location, not just possessing
its prerequisites. Generation verifies every location, including fixed checks.

## Run

Python 3.11 or later:

```powershell
python -m randomizer.standalone --seed 42 --output dist/example-seed.json
python -m randomizer.standalone --catalog my-catalog.json --seed 42 --output dist/seed.json
python -m unittest discover -v
python tools/build_apworld.py
```

The old `python -m randomizer <catalog> --seed ... --output ...` interface still
accepts version-1 catalogs. Its legacy rules do not model regions or events.

Install `dist/sticker_star.apworld` in Archipelago 0.6.8's `custom_worlds`
directory, restart Archipelago, and generate with this YAML:

```yaml
name: StickerTester
game: "Paper Mario: Sticker Star (Logic Demo)"
"Paper Mario: Sticker Star (Logic Demo)":
  progression_balancing: 50
  accessibility: full
```

AP handles multiworld fill. Fixed rewards become local addressless locked
checks; randomized checks and items have stable numeric IDs. Each vector
becomes an AP entrance, and completion requires the fixed victory token.
The output records remote item ownership, but there is no network client
to deliver those rewards to the ROM. IDs are provisional for the demo;
real checks need an explicitly maintained permanent ID registry.

## Version-2 catalog shape

```json
{
  "format_version": 2,
  "items": [
    {"id": "hammer", "name": "Hammer"},
    {"id": "victory", "name": "Victory"}
  ],
  "regions": [{"id": "menu", "name": "Menu", "starting": true}],
  "locations": [
    {"id": "gift", "name": "Gift", "region": "menu"},
    {"id": "end", "name": "Victory Check", "region": "menu",
     "type": "end_goal", "item": "victory", "requires": {"item": "hammer"}}
  ],
  "paths": [],
  "pool": ["hammer"],
  "starting_items": []
}
```

An event item adds `"location": "check_id"` to its item definition.
Paths contain `id`, `forward`, and `reverse`; each vector has `source`,
`target`, and optional `requires`. Rules support `item`, `count: [ID, N]`,
`all`, and `any`, recursively. Missing rules mean unconditional access.

## Playable integration still required

The supplied dump's primary partition identifies title `00040000000A5F00`,
product `CTR-P-AG5P`, in an NCSD container. Direct content inspection confirms
that it is decrypted, despite its original encryption flags. The read-only
inventory tool enumerates 3,887 RomFS files and four ExeFS files:

```powershell
python tools/inspect_rom.py "path/to/Mario Sticker Star.3ds" --output dist/rom-inventory.json
```

Initial inspection found 796 files under `Script`, including `KSMR`-format
world-map and goal-block scripts, and `KDMR`-format item, shop, and map tables
under `Data`. These binary formats and their command semantics still require
reverse engineering before a verified reward patch can be implemented.
No extracted game content is committed; the source ROM remains untouched.

## Experimental real-game patch

```powershell
python tools/build_sticker_patch.py "path/to/Mario Sticker Star.3ds" --seed 42 --output dist/game-patch-42
```

This produces `romfs/Data/kdm_dispos_data.bin` and a JSON report. It shuffles
390 directly placed combat stickers across eligible rooms, preserving the pool.
Seed 42 changes 369 placements. Secret Doors, Things, scraps, HP upgrades,
coins, opening/tutorial rooms, random-choice pickup lists, and shops remain
vanilla in this experimental mode. It does **not** implement generic-sticker
unlock items, shuffled progression, new check categories, or AP delivery.

To test in the supplied Citra Qt build, put the generated `romfs` folder beneath
`%APPDATA%/Citra/load/mods/00040000000A5F00/`. Back up any existing mod first;
do not combine different generated placement tables. The source dump remains
untouched. Removing that replacement file restores vanilla placement data.

Validation on the supplied dump: all 66 KDM tables parse; all 796 scripts were
decompiled using the external Gibberish compiler in a research folder. Ten
generated real-game table patches passed independent byte-range checks: only
the selected four-byte item pointers change. The original table SHA-256 is
`07e25f1d0d730730cec46cd41b565e9bc82b8cdb17bf2ee7daf7c7e5516d33fd`.
An isolated Citra Qt `608383e` boot loaded the replacement and answered live
memory reads matching the extracted game executable. A complete playthrough
and save/reload pickup verification have **not** been performed.

The Citra command-line build crashed with both vanilla and patched data in the
test environment. The Qt build worked with copied settings. Tests used a
separate profile in `.validation/emulator/user`; the regular emulator profile
and saves were not modified.

Research references: [Gibberish source](https://github.com/Longboost/gibberish),
[European game decompilation](https://github.com/Darxoon/leaflitter),
[save editor source](https://github.com/Brionjv/Paper-Mario-SS-Save-Editor), and
[KDM format reference](https://papermariotkb.wiki.gg/wiki/Sticker_Star_KDM_Reference).
Research tool sources and extracted game data stay in ignored `.validation/`.

### Tutorial skip test

```powershell
python tools/build_tutorial_skip.py "path/to/Mario Sticker Star.3ds" --compiler "path/to/gibberish/main.py" --output dist/tutorial-skip-fix
```

This separate experiment keeps the opening movie and skips the field tutorial
to Decalburg's unrolling event. Replace the previous test's whole `romfs` folder
and start a new save slot. Revision 2 changes both the introductory plaza script
and one string pointer in the exit table. It uses the east arrival, whose vanilla
script starts unrolling; the earlier northeast arrival prepared the Toads but
never started that event and could trap Mario among them. Inventory now uses
the regular `item_try_addpouch` command instead of the debug inventory preset.
It grants the hammer, four Jump stickers, four Hammer stickers and two Mushrooms.
This mode does not shuffle stickers or repair existing softlocked saves.

Compilation, canonical decompilation, strict typing and the entrance pointer's
byte boundaries have been verified. On 2026-10-08 the user confirmed successful
arrival, Decalburg unrolling, four Jump/boot stickers, four Hammer stickers,
two Mushrooms and normal movement afterward. Save/reload and subsequent game
progression still need validation. The test's hardcoded hammer/stickers must
be reconciled with the production seed's starting inventory and ability gates.
A Windows crash report for the user's intro crash identifies Intel's
`igxelpicd64.dll` as the faulting module. The isolated test boots with Vulkan;
this does not establish that Vulkan fixes all crashes.

The full remaining architecture, gameplay, standalone, Archipelago 0.6.8 and
validation checklist is maintained in [PATCH_TODO.md](PATCH_TODO.md).

Required next work: verified game check/exit catalog, save flags, reward and
ability hooks, shop behavior, emulator communication, and an end-to-end tested
ROM patch. The existing tracker catalog is provisional and is not silently
treated as verified game logic.

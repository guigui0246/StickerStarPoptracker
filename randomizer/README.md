# Typed Sticker Star randomizer

The typed generation engine works without external packages. The Archipelago
adapter targets 0.6.8. Both use the same `GameDefinition`, rules, regions, and
fixed rewards. The bundled catalog is explicitly a **logic demonstration**,
not a complete Sticker Star randomizer. No ROM patch or emulator client is
implemented; generation output cannot yet be played in the game.

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
No game data is bundled or altered.

Required next work: verified game check/exit catalog, save flags, reward and
ability hooks, shop behavior, emulator communication, and an end-to-end tested
ROM patch. The existing tracker catalog is provisional and is not silently
treated as verified game logic.

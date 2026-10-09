# Maintaining the native randomizer

This guide covers the ROM-derived standalone workflow and the shared native AP
catalog integration. Gameplay verification is deliberately left to the user.
Compiled patches and passing tests establish implementation consistency; they
do not establish that an arbitrary no-logic seed can reach Bowser.

## Generate, install and track

Run this command from the repository with Python 3.12 or newer. Replace the ROM
placeholder with your local path. The included compiler builds the mod
automatically; no separate patch/apply command is needed.

```text
python -m randomizer generate --logic no-logic "ROM.3ds"
```

Seed defaults to random, printed before generation. Output defaults to
`generated/sticker-star-SEED/`. Add `--seed 100` for reproducibility and
`--output generated/my-seed` to select a directory; `--output my-mod.zip` selects
the archive filename and places matching recipe/sidecars beside it. Settings
listed below go on `generate` directly. Existing outputs are preserved.

Extract the ZIP. Install its `00040000000A5F00` directory in the emulator's
`load/mods` directory. Use a fresh save. Generation copies the exact compiled
patch report beside the recipe automatically. Keep all sidecars together;
do not reuse a report from another build.

Load the generated `.stickerpatch.tracker.zip` into PopTracker. Enable emulator
UDP RPC on port 45987 and run:

```text
python -m pip install "websockets>=13,<16"
python -m randomizer track --seed generated/sticker-star-SEED/seed.stickerpatch
```

Connect PopTracker's Archipelago interface to `localhost:38281`, slot `Player`,
without a password. The bridge reads native receipts. It does not grant items
or accept tracker check packets as evidence of collection. Local rewards work
without this bridge. Receipts replay after reconnect; collection and delivery
are separate so a full inventory does not falsely report an item received.

The frozen CLI accepts the same arguments after replacing `python -m randomizer`
with `cli_randomizer.exe`. The compiler is included in release builds too.
`--compiler` overrides it for advanced development. The older `patch generate`
and `patch apply` commands remain available for sharing/reapplying recipes.

## Implemented settings

Both catalog generation and no-logic generation accept these options. The native
AP world has equivalent choices for these six settings.

| Option | Values | Meaning |
| --- | --- | --- |
| `--album-pages` | `all_at_start`, `randomized`, `vanilla` | Eight pages initially; six shuffled upgrades; or native capacity/grants unchanged. |
| `--banners` | `original`, `reduced`, `off` | Original checks, thresholds rounded upward to one tenth, or no banner checks. |
| `--museum` | `all`, `off`, `normal`, `things` | Choose donation checks, without removing native donation gameplay. |
| `--enemy-rewards` | `on`, `off` | Choose first-victory enemy checks. Royal boss sources and victory remain. |
| `--door-stickers` | `randomized`, `vanilla` | Shuffle door-place capabilities or precollect them. Secret Door sticker ownership and native puzzle prerequisites remain separate. |
| `--generic-stickers` | `enabled`, `disabled` | Randomized generic unlocks or native generic sticker availability. Thing unlocks remain randomized. |

Generic classification comes from observed copy/unlock pairs. Disabled mode
removes generic unlock guards, retains original shop/initializer bytes and uses
direct sticker-copy grants. It also removes generic entitlement predicates from
the filled graph. A generic starting unlock becomes its physical copy.

Filters preserve fixed events and EndGoal. Removed checks consume surplus
nonprogression filler first. If the remaining checks cannot hold progression,
generation fails with an explanation; it never discards progression silently.
For no-logic, repeat `--start-with REWARD_ID` to precollect selected observed
capabilities and free pool space. IDs appear in the exported catalog. Victory,
fixed events and pages cannot be selected this way. For an authored catalog,
edit `starting_items` and `pool` together.

`infinite` album capacity is explicitly unsupported. Eight pages are not an
unlimited inventory. Implementing this requires native inventory/menu/battle/
save-format research, beyond changing the page count.

## Experimental world-map controls

No-logic generation additionally supports `--starting-level random`.
Ground routes are opened by default by the one-command generator; use
`--no-open-ground-routes` to request vanilla navigation.
The random start selects an observed ground stage A–E,
grants its admission capability and sets its initial world-map position once
per seed/save. Decalburg and 1-1 are the default starting admissions otherwise.
Hammer and Paperization remain bootstrap items. A physical starting Jump copy
converts to a small slipper while locked; its unlock stays in the shuffled pool.

Open-ground-routes calls the native world-map setter for observed ground
connection flags after the native map update. It excludes sky routes and boat
nodes X01/X02 and does not set stage-clear, Royal or source reward receipts.
Ground nodes are explicitly shown separately from route flags. Stage admission
still needs the corresponding access reward. The map setter's
runtime/save behavior, starting camera and later native refreshes need gameplay
verification. The map patch is not a solved physical graph.

## Add real logic without rediscovering the ROM

The permanent editable registry is `randomizer/data/game/`. Edit typed objects
in `items.py`, `locations.py`, `regions.py`, `paths.py`, `pool.py` and
`starting_items.py`. Every location and directional vector has explicit `Rules`.
`python -m randomizer generate --logic catalog "ROM.3ds"` reads this directory
directly and validates/rebinds Python logic changes against the shipped native
reference in memory. Leave `bindings.json` and `native_reference.json` unchanged
for ordinary logic work. Its initial Menu spokes are no-logic placeholders.
See `randomizer/data/game/README.md` for Python authoring examples. The JSON
examples below describe the legacy interchange format, not the authoring source.

Unlock rewards and physical copies are distinct. A Giant Slipper unlock is a
valid assigned reward and grants an actual Giant Slipper; conversion always uses
the small slipper. Only the exact received sticker type becomes available; it
does not unlock all Jump/Hammer/slipper variants at once.

Each catalog-based recipe exports `.catalog.json` and `.bindings.json` alongside
the tracker sidecars. The catalog contains room regions, item identities, check
identities, fixed victory, starting inventory and the pool. Regions without
checks are included when their scripts were observed.

The generated `...` paths are unconditional Menu spokes. They are
placeholders for generation, not evidence that the player can walk between
rooms. Replace them with actual directed physical links. Global enemy and museum
checks have category regions: assign their accessibility deliberately rather
than treating the first observed encounter as their only physical location.

Rules use one predicate per object:

```json
{"all": [{"item": "ability/hammer"}, {"any": [{"item": "stage_access/A01"}, {"item": "stage_access/A02"}]}]}
```

`{"all": []}` is unconditional. `{"any": []}` is impossible. Item IDs must
already exist. A location's `requires` expresses its own interaction; a path's
direction rules express traversal. Forward and reverse directions can differ:

```json
{
  "id": "physical/example",
  "forward": {"source": "room/SOURCE", "target": "room/TARGET", "requires": {"item": "ability/paperization"}},
  "reverse": {"source": "room/TARGET", "target": "room/SOURCE", "requires": {"all": []}}
}
```

Replace the example room names with observed region IDs. Count predicates have
the form `{"count": ["ITEM_ID", 2]}` in the engine, but native boolean
capabilities cannot represent counted possession and reject such bindings.
Do not give fixed event or EndGoal locations shuffled rewards. Winning the
abstract solver is not a substitute for the native Bowser victory receipt.

Keep an untouched original catalog, then update the binding digest after editing:

```text
python tools/rebind_native_catalog.py --previous-catalog original.catalog.json --catalog authored.catalog.json --bindings original.bindings.json --output authored.bindings.json
python -m randomizer generate --logic catalog "ROM.3ds" --catalog authored.catalog.json --bindings authored.bindings.json --seed 101
```

The packaged CLI exposes the same helper as `cli_randomizer.exe rebind` with
the same arguments. From source, `python -m randomizer rebind` also works.

Rebinding validates both catalogs and the exact native item/location contracts.
It does not rediscover new native sources. For new sources use the production
catalog/binding tools and update the source mapper. Keep released IDs and the
append-only tracker/AP registry stable. Use the same authored catalog for
standalone generation, AP rules and tracker definitions.

## Extend cutscene skips carefully

Existing opening/tutorial and reward-dialogue patches cover their mapped scenes.
There is also an explicit cleanup-callback extension: pass `--scene-skips FILE`
to either catalog generation command, with a JSON list such as:

```json
[{"script_file": "Script/Map/ROOM/room.bin", "entry": "timeline", "cleanup": "finish"}]
```

These are examples, not verified game bindings. Inspect the decompiled script
and choose actual zero-argument functions. The patch replaces only the entry's
body with `finish*(); return*();`. It preserves other functions and rejects
entries containing injected randomizer callbacks, preventing accidental removal
of delivery hooks. Compilation verifies the callback declaration and script
shape. It cannot prove that cleanup performs every necessary story/camera/input
effect; inspect and test those effects before publishing a binding. Never select
a general gameplay function merely because it contains a long animation.

## Where to change the implementation

| File/module | Responsibility |
| --- | --- |
| `randomizer/domain/`, `randomizer/data/game/` | Domain classes and explicit typed Python production objects. |
| `randomizer/data/catalog.py` | JSON interchange boundary and serialization of typed authoring objects. |
| `randomizer/data/no_logic.py` | ROM-derived bootstrap, room/category regions and progression/filler pool. |
| `randomizer/integrations/rom/production_sources.py` | Discover native source identities and hash their ROM scripts. |
| `randomizer/settings.py`, `rom/native_generation.py` | Shared option validation, graph filtering, seed filling and native binding validation. |
| `rom/native_delivery.py`, `rom/plan_io.py` | Native reward kinds, persistent receipts, plan contracts and serialization. |
| `rom/native_recipe.py`, `rom/reward_patch.py` | Asset-free recipe, source validation, script/hook compilation and build report. |
| `rom/stickers.py`, `rom/access.py`, `rom/doors.py` | Entitlement guards, map admission/navigation and door-place policy. |
| `rom/scene_policy.py` | Validated scene-entry to cleanup substitution. |
| `integrations/citra/native.py`, `track_standalone.py` | Read native receipts using the exact patch profile and expose standalone tracking. |
| `integrations/archipelago/native_world.py` | Native AP choices, shared catalog rules and recipe output. |
| `integrations/archipelago/tracker_catalog.py`, `tracker_pack.py` | Stable registry mappings, settings and generated tracker pack. |
| `tools/rebind_native_catalog.py` | Safely refresh catalog identity after logic edits. |

Paths abbreviated `rom/` are under `randomizer/integrations/rom/`; integration
paths are under `randomizer/`. Start with the small tests for the corresponding
module before changing the production source mapper.

Collection receipts indicate the native source was consumed. Delivery receipts
indicate its assigned reward was actually granted. Keep them independent and
retry pending rewards when inventory has space. Ownership is separate from
native source effects: receiving a Royal before its boss must not mark that
boss defeated. AP sequence/acknowledgment and host-only fields have distinct
owners; the standalone tracker must remain read-only. World-map-only fields
are registered in save storage but verified in their own compiled script.

## Checks and remaining work

```text
python -m unittest discover -s randomizer/tests -t .
python -m flake8 randomizer tools build.py --max-line-length=127
pyright
python build.py cli_randomizer apworld tracker --output generated/my-release
```

Relative test imports require `-t .`. Pyright uses `pyproject.toml`; select the
same working Python interpreter in VSCode/Pylance. If Windows redirects `python`
to a broken Store shortcut, invoke your installed Python executable directly and
pass that path to `pyright --pythonpath PATH`.

`human_tests.todo` is the gameplay checklist. Record seed, settings, patch report,
emulator build and save state for each failure. A missing tracker check suggests
source receipt/profile mapping; a checked location without an item suggests a
pending grant/inventory problem; an item without the expected access suggests a
capability guard or native story prerequisite. Preserve the report and assembly
to inspect the original and patched callback together.

Still requiring implementation/research: unlimited capacity, enemy soul/admission
policies, shop-purchase plando (conversation checks are not purchase checks), a
reviewed complete physical progression graph, and exhaustive native source/
formation classification. The general scene extension does not supply bindings
for every cutscene. Real AP multiworld, every reward family, save/reload, full
inventory, settings combinations and full playthroughs still need verification.
See `randomizer/PATCH_TODO.md` for the original broader definition of done.

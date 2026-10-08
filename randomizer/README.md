# Typed Sticker Star randomizer

The typed generation engine works without external packages. The Archipelago
adapter targets 0.6.8. Both use the same `GameDefinition`, rules, regions, and
fixed rewards. The bundled catalog is explicitly a **logic demonstration**,
not a complete Sticker Star randomizer. An experimental combat-sticker ROM
override and a Citra memory transport are now implemented. The full progression
patch remains unfinished. Native check hooks, reward delivery, a durable AP
client and optional standalone tracker connection now exist as experimental
integrations; full-game access logic and emulator playtests are still required.

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
The output records remote item ownership. The native client is a separate
integration requiring actual patch selectors and check mappings; demo output
cannot be installed as a playable patch. IDs are provisional for the demo;
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

### Shareable seed recipes and combined tutorial skip

Generate an asset-free recipe, then apply it to your own decrypted European dump:

```powershell
python -m randomizer.patch generate "path/to/Mario Sticker Star.3ds" --seed 42 --tutorial-skip --output dist/seed-42.stickerpatch
python -m randomizer.patch apply dist/seed-42.stickerpatch "path/to/Mario Sticker Star.3ds" --compiler "path/to/gibberish/main.py" --output dist/combined-seed-42
```

Omit `--tutorial-skip` to preserve the vanilla tutorial; that mode needs no
compiler. The external Gibberish compiler currently needs Python 3.13 or later
(the combined build was verified with Python 3.14). Run the application command
with that interpreter when enabling the tutorial skip.

The `.stickerpatch` is a versioned JSON recipe containing only the seed,
supported mode, tutorial revision, file hashes and pickup count. It contains
no ROM bytes, scripts, assets or spoiler placements. It binds the source files
and generated sticker table to exact SHA-256 hashes. Corrupt recipes, unknown
fields, unsupported versions, different source files and changed algorithm
outputs are rejected before mod files are published. Checksums detect accidental
changes; they are not signatures establishing the identity of a seed's author.

Application builds in a temporary sibling folder and publishes the completed
mod only after success. Existing output folders are refused, and a failed build
does not leave a partially installed mod. The combined output contains both
the combat shuffle and revision-2 tutorial skip in one `romfs` folder. The source
ROM, installed emulator mods and saves are never modified by these commands.
The generated mod contains locally derived game data; share the recipe instead.

This remains the experimental **combat-sticker shuffle**, with vanilla
progression. Enabling the tutorial skip uses its confirmed test inventory,
including Hammer; it does not implement randomized abilities. It is not the
full progression randomizer and does not supply Archipelago runtime delivery.
The combined build has been checked against the original table and the
previously tested tutorial patch; a combined in-game playthrough remains pending.

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

## Native persistent reward hooks

`tools/build_native_rewards.py` now builds actual KSM overrides for explicitly
assigned mini-star goal-block checks. This is a backend experiment, not a
complete seed generator. It validates each `(map_name, source_flag)` against
one actual `mobj_goal_block_exit` call decompiled from the user's ROM.

Supported reward commands are `item` (native item ID), `coins` (1–9999),
`mini_star` (registered native route flag), and `royal` (index 1–6). Configured
checks suppress their original route reward and request the assigned reward.
Unconfigured checks keep their original behavior. Items such as Hammer and
scraps can use their native IDs, but their complete ability/puzzle gates have
not been patched. `sticker_unlock` grants a copy and unlocks shop stock;
`sticker_copy` grants a filler without unlocking it. In this mode locked generic
copies become `SL_W6_SANDAL_S`. Generic `item` rewards are rejected to prevent
accidental bypass of the unlock/copy distinction.
Raw `SL_PAGE` item rewards are rejected. Select `--album-pages randomized`
and use six `page` rewards with value `1`, or select `--album-pages all_at_start`.
These modes suppress all six observed vanilla page grants. All-at-start grants
six pages once; randomized mode grants upgrades independently. Initialization
requires the native two-page base state and grants cannot exceed eight pages.
Use a fresh save. Native page semantics and save/load still require playtesting.

The backend allocates separate collected/delivered flags inside the unused
gap in `kdm_switch.bin`, below the game's reserved item-flag range. It does not
enlarge save buffers. A 128-bit placement fingerprint binds that reward state
to one placement table. The delivery script uses a non-forced inventory grant;
an unsuccessful grant leaves its delivery flag unset for retry on map entry
and every 30 frames in maps using the common layout helper. Decalburg's custom
initialization also starts the poll. Other custom map initialization still needs
coverage verification. Persistence, delivery retries,
VM thread lifetime and deduplication require actual gameplay/save tests.

Example **build fixture**, with vanilla 1-1 route delivery:

```json
[
  {"map_name": "hei_5_03", "source_flag": "GF_WM_A01_A02",
   "reward": {"kind": "mini_star", "value": "GF_WM_A01_A02"}}
]
```

```powershell
python tools/build_native_rewards.py "path/to/Mario Sticker Star.3ds" --placements placements.json --compiler "path/to/gibberish/main.py" --output dist/native-reward-test
```

Python 3.13+ is needed by the external compiler. Builds use a new output folder
and publish only after both scripts and the save-switch table pass validation.
`--shuffle-royals` requires all six source checks and Royal reward capabilities.
It suppresses the observed vanilla grants and the debug book-restoration routine,
preserving surrounding story flags. Royal access gates and save behavior still
need gameplay validation. The real victory hook checks Bowser's battle result,
so escaping the fight cannot mark victory.

Explicit Thing and scrap placements also accept `map_name`, `object_name`,
`source_item` and `reward`. The builder checks these against one disposition
record and patches the shared `item_get_real_name` and `map_piece_get` handlers.
Unconfigured pickups retain vanilla handling. These hooks compile, but custom
map callbacks, collection persistence and source story effects need gameplay
verification before they can be advertised as complete Thing/scrap shuffling.

## Archipelago runtime and observed event registry

`integrations/archipelago/runtime.py` implements authenticated AP packet state
and a durable SQLite receipt queue bound to seed, team, slot, catalog hash and
save identity. It validates overlapping item packets, requests synchronization
for gaps, persists checks and victory, and replays them after reconnecting.
Installed local placements can deliver offline and share receipts with their
server echoes. Full inventory leaves pending items queued. Native receipts are
read again after save reload or rollback; disk state is never proof of an
in-game grant. `network.py` adds reconnecting WebSockets (`websockets>=13`).
`integrations/citra/native.py` implements the native receipt/mailbox adapter.
It verifies the executable signature and placement fingerprint before writing,
uses separate host/native words, waits for game-owned acknowledgements and binds
the client to a save nonce. Atomicity and nonce persistence across actual saves
still need emulator tests. A successful host write never counts as delivery.

The transport test uses actual WebSockets and AP 0.6.8's own NetworkItem/Version
serialization:

```powershell
py -3.12 tools/test_ap_network.py --ap-root .validation/Archipelago-0.6.8 --dependencies .validation/dependencies312
```

`tools/extract_events.py` extracts exact mini-star calls and actual stage codes
from the user's ROM, with source hashes and stable map/route IDs. The European
dump yields 39 mini-star checks, 41 stage destinations, 160 museum exhibits,
six shop conversations and three Kamek completion signals. Separate maps that
share a route flag remain separate checks. Stage-code order is not assumed to
match level order. This manifest records observed events, not verified puzzle
rules or a complete game catalog.

## Native recipes and client

Native `.stickerpatch` format 2 contains explicit check/reward metadata,
settings, ROM SHA-256, the save fingerprint and optional remote selectors and
session identity. Applying it compiles scripts from the recipient's own ROM.
Recipes contain no extracted scripts or game assets.

```powershell
python -m randomizer.patch generate-native ROM.3ds --seed my-seed --placements placements.json --output seed.stickerpatch
python -m randomizer.patch apply seed.stickerpatch ROM.3ds --compiler path/to/gibberish/main.py --output dist/my-mod
```

Add `--remote-rewards selectors.json --ap-session session.json` for a mailbox.
The session requires `seed`, `team`, `slot`, and `catalog_hash`; selectors require
`item_id` and a native `reward`. Allocation rejects plans exceeding the existing
save-flag gap, without enlarging the buffer or using reserved item flags.

119 generic unlocks receive gated stock in all generic shops. 64 Thing stickers
map to their corresponding Thing-shop entries. Field pickups pass through the
conversion handler. Battle drops/direct additions still need coverage checks.
Thing filler copies do not unlock their Thing-shop entries. Opening and dialogue
skip experiments retain surrounding setup and message-seen flags, but native
startup remains unverified: the isolated emulator loads overrides and the code
patch, yet recorded startup inputs have not reached seed initialization.

```powershell
python -m randomizer.client --patch-report dist/my-mod/patch-report.json --locations locations.json --local-rewards local-items.json --name Player --state state.sqlite --server ws://localhost:38281
```

The client requires a mailbox-enabled patch report, native-check to AP-ID mapping,
and local NetworkItems matching installed selectors. Omit `--server` for offline
operation. Local script delivery works independently of the host client.

Optional standalone PopTracker reporting uses `--tracker-data tracker-data.json
--tracker-port 38281`. This read-only endpoint binds to loopback. Its configuration
requires `catalog_hash`, `items` and `locations` name-to-ID maps, and a `tracker`
slot-data object with matching hash and `format_version: 1`. Item mappings use
`{code,type}` (and `max_stage` for progressive items); location mappings use exact
`@Location/Section` codes. Checks and inventory remain independent.

## Native ownership gates

Explicit native rewards now support:

| Kind | Value | Native effect |
| --- | --- | --- |
| `ability` | `hammer` or `paperization` | Save-owned ability flag and filtered native accessory attachment. Both capabilities must be present. |
| `stage_access` | Native stage code, including `X00` for Decalburg | Additional world-map admission gate; existing route and admission checks remain. |
| `door_access` | Numbered native stage code | Rejects a fit at that stage's Secret Door through the native miss/take-back path until ownership is received. |

Ability plans emit both `romfs` and `exefs/code.ips`. Install these folders
together. The ARM guard occupies verified padding inside the existing executable
text pages, checks the save seed fingerprint, and retains unrelated accessory
bits. A network client verifies both patched code ranges before writing memory.

Ability plans also compile a startup experiment that marks the intro/unrolling
and tutorial battle complete, grants only album access, and routes the initial
plaza exit to the world map. It does not grant Hammer, Paperization or sticker
unlocks. World-map delivery polling supports received admission items while on
the map. Gameplay verification of this startup path is still outstanding.

The 38 numbered stages map to 40 observed Secret Door placements. D06, F01 and
F03 have no such placement in the original table. Door admission leaves native
Paperization and sticker requirements intact and never marks a door done itself.
Neither compiled gates nor observed placements constitute a verified puzzle graph.

Validation on 2026-10-08: 92 repository tests, five actual Lua tracker tests,
384 native ARM ability executions, and AP 0.6.8 WebSocket transport checks pass.
Native fixtures compile for all 39 mini-stars, 160 exhibits, six shop callbacks,
112 existing enemy definitions with death callbacks, abilities, all 38 door
capabilities, pages and remote delivery. The enemy table also contains missing
scripts and units without death callbacks; these are not advertised as complete
combat checks. The authoritative catalog, save-capacity solution for the full
combined check set, boss encounter gates and full playthrough remain unfinished.

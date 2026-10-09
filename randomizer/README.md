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
| `boss_access` | `w1`–`w6` or `harbor` | Gates the original encounter callback and restores suspended encounter triggers after ownership arrives. |

Ability plans emit both `romfs` and `exefs/code.ips`. Install these folders
together. The ARM guard occupies verified padding inside the existing executable
text pages, checks the save seed fingerprint, and retains unrelated accessory
bits. A network client verifies both patched code ranges before writing memory.
Each ability build also emits `exefs/abilities.S`: valid ARM assembly containing
the exact patch words, instruction annotations, labels, and seed literal pool.
The checked-in `native/abilities-reference.S` shows the validated RPC fixture;
its seed constants must not be reused for other seeds. The patch builder emits
words directly, so installing a separate assembler is unnecessary.

Ability plans also compile a startup experiment that marks the intro/unrolling
and tutorial battle complete, grants only album access, and routes the initial
plaza exit to the world map. It does not grant Hammer, Paperization or sticker
unlocks. World-map delivery polling supports received admission items while on
the map. Native seed initialization, album initialization and unowned ability
state have been observed in the emulator. Remote coin delivery and both native
ability bits were also confirmed through the actual mailbox. Town presentation,
page-menu behavior and save/reload persistence still need gameplay verification.

The 38 numbered stages map to 40 observed Secret Door placements. D06, F01 and
F03 have no such placement in the original table. Door admission leaves native
Paperization and sticker requirements intact and never marks a door done itself.
Neither compiled gates nor observed placements constitute a verified puzzle graph.

Network-only checks allocate collection state without a local delivery flag.
Native reports represent that absent receipt as `null`; the client never treats
collection as inventory delivery. Compact layouts have a distinct save
fingerprint, preventing older layouts from being interpreted at shifted indices.
`tools/check_native_capacity.py` merges observed report fixtures and measures
storage before optionally writing an experimental plan. The 326-check merged
fixture needs 698 of 1114 available bits. Adding all observed Thing/scrap
dispositions, banners and Kamek signals produces a corrected 454-record fixture
using 826 bits. It compiles and its client profile loads. The capacity tool
reports excluded obsolete shop-setup hooks; production builds reject them.
These fixtures are not complete progression seeds.

Validation on 2026-10-08: 163 repository tests, five actual Lua tracker tests,
384 native ARM ability executions, 17,760 sticker-guard ARM executions,
and AP 0.6.8 WebSocket transport checks pass.
Native fixtures compile for all 39 mini-stars, 160 exhibits, six shop callbacks,
112 existing enemy definitions with death callbacks, abilities, all 38 door
capabilities, pages and remote delivery. The enemy table also contains missing
scripts and units without death callbacks; these are not advertised as complete
combat checks. The authoritative catalog, boss encounter gameplay and full playthrough
remain unfinished. The tested 425-check all-local/incoming fixture now fits.
All seven boss gates compile, including a combined Royal replacement fixture;
compilation alone does not establish encounter behavior or progression safety.

## Generate a native recipe from a typed catalog

`python -m randomizer.patch generate-native-catalog YOUR_ROM --catalog catalog.json
--bindings native-bindings.json --seed SEED --output seed.stickerpatch` solves
the catalog and converts its placements and fixed rewards to an actual native
recipe. Apply it with the existing `apply` command and compiler option.

Bindings use `format_version: 1`, `catalog_sha256`, an `items` object mapping
each catalog item ID to a native `{kind,value}` reward, and a `locations` array
of `{location,source}` entries. `source` uses the existing native check fields
without a `reward`: the generated placement supplies that reward. The hash is
SHA-256 of the catalog JSON with sorted keys, compact separators and UTF-8
encoding with `ensure_ascii=False` (see `native_generation.catalog_digest`).

Both registries must match the catalog exactly. The bridge replays the seed,
requires every enabled check and the goal to be reachable, preserves fixed
victory, and rejects duplicate native sources. Banner and page settings adjust
the typed check/item pool before placement. Starting inventory uses separate
native receipts and retries when the album is full. This command does not
supply the still-unfinished authoritative full-game graph.

## Native Archipelago generation

`python tools/build_apworld.py --catalog catalog.json --bindings native-bindings.json
--rom YOUR_ROM --output sticker_star.apworld` packages the caller's typed catalog
as **Paper Mario: Sticker Star (Native Catalog)**. It includes no game assets.
The generated `.apworld.ids.json` retains item/location numeric IDs across
catalog additions; retain this registry when rebuilding a published catalog.
Generation emits native `.stickerpatch` recipes and matching `.client.json`
files, plus `.tracker.lua` and `.tracker.json` definitions for pack authors
and a `.tracker-data.json` observation-server data package.
The generated tracker predicates use the same typed graph, including both
directions of paths, counts, alternatives and fixed-event closure. Actual Lua
execution matches shared-graph reachability in 18 inventory scenarios. These
definitions still need a complete catalog and a finished tracker presentation.
Apply the patch, then start `python -m randomizer.client --config
OUTPUT.client.json --patch-report MOD/patch-report.json --state client-state.json`
with the usual server option when connecting online.

Actual AP 0.6.8 tests pass ten two-player seeds, page/banner settings and
precollected items using an artificial rules fixture with observed native
sources. A live generated-patch test acknowledges the precollected Hammer
echo and replay without changing native inventory. Full-game AP generation
still needs the authoritative game catalog and progression rules.

The shared native delivery engine commits album additions only after capacity
checks. Live tests verify locked-sticker conversion, native unlock insertion,
starting stickers, full-album rejection/retry and save/reload persistence.
Network page/sticker requests commit once, with sequence 18 acknowledged and
replayed without adding another copy. Existing feasibility-only test saves have
a different fingerprint and must not be reused.

Enemy grouping gives one receipt per observed combat display type while keeping
all associated native callbacks. The current grouped fixture has 419 checks
and 77 selected enemy types. A standalone fixture containing all implemented
reward capabilities and six randomized pages compiles within 1100/1114 bits;
the network-only counterpart uses 986 bits. Larger incoming layouts now use the
compact saved-byte mailbox described below; local flag overflow is rejected.

`python tools/export_native_room_links.py kdm_link_data.bin --output links.json`
exports 1,135 exact directed records from 406 room groups in the inspected dump.
It retains virtual/test exits and both callbacks. These records do not imply
unconditional traversal; callback puzzle requirements still need verification.
Emulator probes use `tools/launch_native_probe.ps1`, which disables audio output
in a disposable profile before every launch.

## Standalone native tracking

`generate-native-catalog` also emits `.tracking.json`, `.tracker.lua`,
`.tracker.json`, `.tracker-data.json` and an append-only `.registry.json`.
Reuse the registry with `--registry` when revising the catalog. After applying
the recipe, run:

```text
python -m randomizer.track_standalone --config seed.stickerpatch.tracking.json --patch-report MOD/patch-report.json --tracker-data seed.stickerpatch.tracker-data.json
```

Connect the matching tracker pack to `localhost:38281` as `Player`. Observation
reads native checks, committed local rewards and starting-reward receipts. It
does not require a delivery mailbox or an Archipelago server, and its memory
adapter rejects every write. Check collection never substitutes for reward
delivery. Save rollback clears/replays the tracker view. Catalog, executable
and seed fingerprints are checked before observations are accepted. The
generated definitions remain building blocks for a finished tracker pack.

The updated native encounter engine stores battle-only pending deaths in shared
script variables, while collection and delivery receipts remain saved. A live
77-type mark/read/reset probe passes; escape/museum/controller combat scenarios
still need gameplay verification. The 423-check capability fixture now uses
890 reserved save bits. A 425-check all-local/incoming fixture uses 1,060
GF bits and 28 previously unused native GS bytes. Native save/reload, exact
acknowledgements, replay and maximum-sequence tests pass. Builds automatically
select this mailbox when the GF layout would exceed 1,114 bits. Five ARM edits
expand the native script-variable arena so this larger fixture can run.
Layouts exceeding the remaining local GF budget are still rejected.

Native puzzle export reads all 177 paperization locks and their exact accepted
input alternatives. The desert gate requires all six independent slots. Fixed
native story events can observe original completion flags without inventing
inventory grants or extra delivery flags. Royal castle admission counts Royals
1–5, so receiving Royal 6 cannot substitute for a missing earlier Royal.
Physical castle and complete progression playthroughs remain unverified.

Door access rewards accept an exact native lock identity such as
`w3_for_04_door`. These unlock only that placement, including stages containing
multiple doors. Legacy numbered-stage rewards remain supported where a door
was observed; overlapping exact and stage-wide rewards are rejected.

Incoming randomized pages now use separate saved receipts, so a later remote
page can add album capacity while an earlier remote sticker waits. This does
not advance the normal item acknowledgement past that sticker. The page is
counted once, including after replay and native save/reload. Starting-page
server echoes do not grant another page. New incoming-page plans automatically
use the GS mailbox with 29 saved bytes and six additional GF receipts; old
explicit recipes retain their original layout and fingerprint. The combined
425-check fixture with all 40 exact doors compiles with 1,071 GF bits.

To audit enemy coverage against the original native formations, run:

```text
python tools/audit_native_enemy_coverage.py --rom YOUR_ROM --patch-report MOD/patch-report.json --output enemy-coverage.json
```

The current combined fixture covers all combat display types and all available
combat variants in 862 observed formations. The audit also exposes unavailable
script records, units without death callbacks and debug formations, preserving
their actual names rather than inventing checks. It does not assert that every
formation is reachable or replace encounter gameplay validation.

### First-peel sources and scrap capacity

Explicit native plans now accept `PeelReward` sources: 17 checks cover the 18
observed peelable scrap variants. The two portrait locks share one reward.
The first successful peel latches a check; restored pieces can be peeled again
without receiving the randomized reward twice. Native restoration inputs,
paired locks and map effects are retained.

Repeat peels reserve native scrap-album space before the pickup sequence. A
committed return uses the separate game-owned `gs_rando_peel_pending` byte and
retries until insertion succeeds. The client cannot write this receipt. The
scrap album has nine fixed pages and is independent of combat album upgrades;
large pieces can exhaust it even with fewer than 18 distinct scraps.

The native helper test passes all first rewards and all 18 bounded returns.
It uses the game's inventory-clear helper between isolated return cases; this
is not a physical peeling/restoration playthrough. The combined 442-check
all-local/incoming build compiles with 1,105 GF bits and 30 GS bytes. Full-game
traversal rules, physical source effects and a complete playthrough remain
unverified.

Independent mailbox commands also support idempotent Hammer/Paperization,
stage, door and boss access, plus shuffled Royal ownership. Their existing
ownership flags provide receipts without acknowledging an earlier blocked
inventory command. Coins, copies and ordinary item grants retain prefix order.
Live tests deliver Paperization, town access and Hammer while a scrap command
is blocked, preserving its acknowledgement, album contents and pending peel
return. The selected-variant pending return and saved identity also survive an
emulator restart without clearing inventory.

Validation on 2026-10-09: 191 repository tests and strict typing across all 73
production modules pass. The 416-check production fixture compiles with observed
unconfigured Paperization targets preserved in rooms containing shuffled peels.
A first-time peel reward succeeds while an older scrap return is queued, and
both persist across an actual restart without clearing inventory.
The received-first Faucet test passes its original full story event, source
visibility, native water effect, replacement prize and replay checks. Its
cross-script water query and all seven shared Thing initializer callers are
evaluated before native conditions. Physical hammer input remains unverified.
The original D02 Curling Stone initializer also passes with its unlock received
first, including native source eligibility, shared acquisition, replacement
prize and replay. The original skiing acquisition callback and its carrier
position/state cleanup also pass with a staged native carrier slot. Skiing
controls remain unverified.

### Native treasure-file sources

`ContainerReward` binds a map and its actual `TREASURE_FILE` object to a
randomized prize. The original opening sequence and chest flag remain intact.
Configured chests suppress the two original inventory grants and source-item
notification; their check and pending prize use separate randomizer receipts.
Unconfigured chests keep their normal behavior. Direct scripted acquisitions
of the same field scrap share the configured chest receipt.

The production table contains three nonempty scrap chests. A fourth matching
record belongs to the `TST` debug group; an empty production story chest has no
reward definition. The inaccessible `map_piece_c` oasis stand-in is replaced
by its actual chest in the combined fixture. All 416 production checks compile
in 1,053 GF bits and 30 GS bytes. The earlier 444-check fixture included 30 debug
Thing pickups and omitted the two scripted Things; those source identities are
now corrected. Physical chest opening still requires validation.

`tools/audit_native_scrap_coverage.py` accounts for all 58 real scrap inventory
descriptors without treating restoration variants as extra checks. The four
Wiggler inputs remain story evidence. Complete restoration requires four
distinct segments despite every native slot accepting any of them; this rule
is available to the shared catalog through `wiggler_restoration_requirements`.

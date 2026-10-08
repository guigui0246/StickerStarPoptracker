# Sticker Star randomizer implementation checklist

Target: Azahar/Citra first. The supplied NCSD dump has primary title ID
`00040000000A5F00`, product code `CTR-P-AG5P`, and decrypted ExeFS/RomFS content
(verified directly, rather than inferred from the original NCCH flags).
Playable patch work needs decoded script/table formats and verified event mappings.
The typed domain, standalone engine, and Archipelago 0.6.8 example integration
are implemented; see `README.md` in this folder for their limits.

This checklist records the original architecture request and the gameplay rules
in `SPEC.md`. Checked entries distinguish implemented foundations from actual
gameplay validation. The complete standalone and Archipelago randomizers are
still unfinished.

## Native integration progress — 2026-10-08

- [x] Compile persistent museum checks for all 160 actual production exhibits,
      with native donation flags separate from possession and delivery.
- [x] Compile native banner checks using original thresholds or exact rounded
      one-tenth comparisons; disabled banners can be omitted from the plan.
- [x] Compile six real shop conversation callbacks and three Kamek completion
      signals; correct Decalburg's callback to `talk_kinopio_shop`.
- [x] Compile all six Royal source replacements, vanilla grant/restoration
      suppression, and a Bowser victory hook that excludes escape results.
- [x] Implement native generic unlock/copy commands, 119 unlock flags, stock
      expansion in every generic shop, field-item conversion and 64 Thing-shop
      mappings. Battle drops/direct additions and full-album pickup retention
      still need gameplay coverage verification.
- [x] Implement a signature-checked native RPC mailbox with separate ownership,
      game-owned receipts, retry, save fingerprint and bound network session.
- [x] Implement the runnable native AP client and offline operation, durable
      local-placement binding, AP replay deduplication and rollback checks.
- [x] Implement optional loopback pseudo-AP tracking and actual PopTracker Lua
      callbacks; location reports never grant inventory and rollback reconnects.
- [x] Extend asset-free native `.stickerpatch` recipes to explicit check/reward
      plans, settings, unlock policies and optional remote selector/session data.
- [x] Compile language-independent opening and native dialogue skip experiments.
      Menu behavior, scene transitions and remaining cutscenes are unverified.
- [x] Compile 112 existing enemy definitions with native death callbacks;
      clear pending encounters at battle start and commit only on victory
      outside museum battles. Full combat-type classification remains pending.
- [x] Compile native Hammer/Paperization ownership and a seed-bound ARM
      attachment filter in existing executable padding. Verify 384 native ARM
      executions, preserved registers and bounded writes; gameplay pending.
- [x] Compile additional world-map stage admission gates, including Decalburg,
      retaining native route/admission checks and supporting local/remote grants.
- [x] Compile all 38 numbered-stage Secret Door capabilities for 40 observed
      placements, using the native miss/take-back path before fit completion.
      Gameplay/sticker retention verification remains pending.
- [x] Compile an ability-safe post-tutorial/world-map startup experiment and
      world-map delivery poll. The emulator loads the patch but recorded startup
      inputs have not reached seed initialization; do not call startup verified.
- [x] Validate 92 repository tests, five real-Lua tracker tests, strict typing
      of changed native modules and AP 0.6.8 wire transport.
- [ ] Verify the combined 205-check fixture's native initialization, reward
      collection, save/reload and inventory retry in gameplay. It compiles; it
      is not a complete catalog or a solvable progression seed.

The remaining unchecked requirements below still apply, especially native gate
gameplay, boss encounters, combat-type classification, the authoritative puzzle graph,
production starting-state handling, complete AP generation and full playthroughs.

## Confirmed tutorial test — 2026-10-08

- [x] Build a separate tutorial-skip patch for the supplied European dump.
- [x] Correct the arrival to use the entrance that starts the unrolling event.
- [x] User confirmed arrival and Decalburg unrolling work.
- [x] User confirmed the book contains four Jump/boot stickers, four Hammer
      stickers, and two Mushroom stickers.
- [x] User confirmed normal movement after unrolling.
- [ ] Verify save/reload, repeated fresh starts, hammer use, subsequent tutorial
      battle, and departure from Decalburg with this patch.
- [ ] Integrate the skip into production starting-state handling. Its hardcoded
      hammer and stickers are test fixtures, not shuffled progression logic.
      Preserve the unique Menu starting region and item-gated Decalburg access;
      do not let the skip bypass configured Hammer/Paperization or page gates.

## Required startup and dialogue skips

- [ ] Skip the intro, all long cutscenes, and textboxes regardless of the
      selected game language. Preserve required event flags and progression.
- [ ] Initialize Decalburg in its post-tutorial-Goomba state, with the town
      already unrolled and the tutorial Goombas already defeated. Preserve
      configured randomized abilities and the Menu-to-Decalburg access gate.
- [ ] Validate these skips and the starting state primarily in English, with
      additional tests in other supported languages.

## Required typed architecture

The required classes already exist in `domain/`. The remaining work is to use
their contracts throughout the real game catalog, patch and clients.

| Class | Required contract | Foundation |
| --- | --- | --- |
| `Location` | A check where an item is received, belonging to a region and governed by rules. | Implemented |
| `Item` | A clearly identified reward with progression classification. | Implemented |
| `Event` | A special item at one specific location; never randomized. | Implemented |
| `Goal` | A special location with one specific fixed item; never randomized. | Implemented |
| `EndGoal` | A fixed Goal whose actual completion marks the randomizer won. | Implemented |
| `Region` | A group of locations with any number of paths, including alternative paths. | Implemented |
| `Vector` | One directed traversal between regions, with its own rules. | Implemented |
| `Path` | A two-way connection with exactly two opposing vectors and independent rules. | Implemented |
| `StartingRegion` | Exactly one unconditional starting region: the main menu/map, distinct from Decalburg. | Implemented and validated |
| `Rules` | Requirements for collecting a location or traversing a vector, supporting all/any/counts. | Implemented |

- [x] Separate domain, catalog, standalone, Archipelago, ROM and Citra code into
      folders and subfolders; preserve the old prototype under `legacy/`.
- [x] Validate references, pool size, the unique starting region, fixed rewards,
      opposing vectors and the victory goal in the shared model.
- [ ] Populate these classes with the verified full-game catalog and real fixed
      events/goals. Demo data and provisional tracker data are insufficient.
- [ ] Keep one authoritative rules model for standalone, Archipelago and tracker
      adapters, including different requirements in each direction of a path.
- [ ] Replace remaining legacy/prototype behavior in production entry points;
      keep game-specific binary formats and emulator/network details in adapters.
- [ ] Apply strict typing to every production module and avoid untyped catalog,
      patch-state and network-state boundaries.

## Game inspection

- [ ] Record region, revision, title ID, and hashes of the user's own dump.
- [x] Inspect primary partition and enumerate 3,887 RomFS files and four ExeFS files.
- [x] Identify KSMR scripts and KDMR item/shop/map tables as investigation targets.
- [x] Parse all 66 KDM tables with typed views; preserve raw bytes for same-size edits.
- [x] Decompile all 796 game scripts for local research (external Gibberish tool).
- [x] Map 964 disposition item records to 227 room IDs and original collection flags.
- [x] Produce a real experimental combat-sticker patch and confirm loading in Citra Qt 608383e.
- [x] Validate the Citra UDP transport with live executable-signature reads.
- [x] Extract game tables/scripts and the executable for local research.
- [ ] Finish identifying event scripts, shop stock, inventory, ability flags,
      stage exits, museum records, and save flags and verify their semantics.
- [x] Document Citra LayeredFS mod loading and replacement-file installation.
- [ ] Verify other supported emulator versions/platforms before advertising them.
- [ ] Reconstruct the complete check catalog with stable IDs: mini stars, Things,
      bosses, Kamek fights, first victory per enemy type, scraps, shop Toads,
      museum exhibits, and success banners with original thresholds.
- [ ] Map every mini-star reward to its exact exit, including alternate exits and
      shortcuts. Verify the tracker's provisional routes against game event IDs.
- [ ] Implement one door-place unlock per numbered level. The tracker now has
      all 38 items; map these IDs to game events and apply them to every actual
      door interaction. Towns have their own tracker maps and check groups.

## Reward hooks and persistence

- [x] Compile shared Thing/scrap pickup dispatch for explicitly validated native
      map/object/item placements; preserve unconfigured pickup handlers.
- [x] Compile a baseline covering all 39 observed mini-star calls and add
      delivery polling to Decalburg's custom initialization.
- [ ] Verify Thing/scrap source effects, callback coverage and persistence.

- [x] Implement a native script backend for explicitly mapped goal-block checks,
      with separate collected/delivered flags and pending non-forced item grants.
- [x] Allocate named global save flags within the unused registry gap, preserve
      existing tables and bind the reward flags to a placement fingerprint.
- [x] Compile/decompile fixtures for mini-star, item, coin and Royal commands.
- [ ] Verify this backend's native collection, full-album retry, save/reload,
      thread lifetime and wrong-seed rejection in gameplay. An isolated emulator
      reaches the title screen, but controller automation did not work.
- [ ] Shuffle all six Royal Stickers, Hammer, Paperization, individual mini-star
      exit items, boss unlocks, scraps and numbered-level door-place unlocks.
- [ ] Replace vanilla rewards at all randomized checks; prevent double rewards.
- [ ] Grant Royal Stickers and mini stars without tying them to the source boss
      or stage. Open the destination encoded by the received star.
- [ ] Gate Hammer, Paperization, bosses, scraps, and door places by received items.
- [ ] Thing sticker rewards: grant one sticker and unlock the Thing shop entry.
- [ ] Generic sticker rewards: grant one copy and unlock the sticker in all shops.
- [ ] Convert locked ordinary sticker pickups (? blocks, enemy drops, etc.) into
      Kamek flip-flops; bypass conversion when receiving an unlock reward.
- [ ] Implement coins and sticker copies as fillers. Filler copies obey the
      locked-sticker conversion rule and never silently unlock their sticker.
- [ ] Verify whether ordinary Thing sticker pickups need a separate conversion
      rule; keep this unresolved distinction explicit until confirmed.
- [ ] Keep museum donation checks separate from sticker possession/shop unlocks.
- [ ] Persist collected checks and unlocks across saves, reloads, and emulator restarts.
- [ ] Hook first victories globally per enemy type, each Kamek fight, first
      conversations with shop Toads, scraps, mini stars, boss rewards, banners,
      and every individual museum exhibit, including Thing exhibits.
- [ ] Keep fixed Events and Goals at their declared locations, exclude their
      rewards from the shuffled pool, and make the real EndGoal trigger victory.

## Settings and logic

- [x] Add strict shared album/banner settings and rounded reduced thresholds.
- [x] Build album overrides suppressing the six observed vanilla page grants;
      compile independent +1 rewards and once-only all-at-start grants with
      two-page initialization/eight-page upper bounds. Gameplay verification pending.

- [ ] Add the `album_pages` setting: all eight at start (default), or two base
      pages plus six randomized +1-page rewards in the existing reward pool.
- [ ] Disable vanilla page grants from Royal Sticker cutscenes and the 1-3 Toad
      in shuffled mode, preventing duplicate or unintended capacity upgrades.
- [ ] Keep page-upgrade rewards independent of Royal Sticker ownership and boss
      check completion. Persist the selected mode and received page count.
- [ ] Verify that two starting pages can hold all required early-game stickers;
      account for large Things and simultaneous sticker requirements in logic.
- [ ] Investigate experimental unlimited capacity: inventory storage, page menus,
      placement, battles, shop purchases, overflow behavior, and save/load.
      If literal infinite pages are impractical, evaluate expandable storage or
      an overflow inventory. Do not write beyond the original inventory buffer.

- [ ] Implement disabled success banners by removing their checks from the pool.
- [ ] Implement divided banner thresholds, minimum one; confirm rounding for
      thresholds not divisible by ten. Prototype currently rounds upward.
- [ ] Verify puzzle prerequisites, alternative Thing solutions, boss availability,
      Wiggler/harbor events, Royal Sticker gates, and starting abilities.
- [ ] Replace tracker entrance overrides with exact gates after reconstruction.
- [ ] Share the verified catalog between seed generation and tracker logic.
- [ ] Decide whether boss battle tools are required or merely recommended; do
      not make an optional weakness sticker a hard progression lock.

## Seed delivery and tracker connection

- [x] Make the experimental combat-sticker generator output a `.stickerpatch` file containing
      no copyrighted game/IP assets or ROM content, for legally shareable seed
      distribution. Apply it later to the user's own ROM to generate the mod;
      keep ROM-derived content out of the distributable patch artifact.
- [x] Validate recipe versions, supported settings, source file hashes and
      expected generated placement hashes; build into a new mod folder atomically.
- [x] Combine the combat shuffle and confirmed revision-2 tutorial skip in one
      generated mod, preserving the original ROM and installed emulator state.
- [ ] Extend `.stickerpatch` recipes to the complete progression catalog and
      persistent local/remote delivery after the game hooks are implemented.
- [ ] Load the seed's reward table into the patch; verify catalog/version hashes.
- [ ] Implement an emulator-to-PopTracker connection for received inventory and
      completed check flags, maintaining separate state for each.
- [ ] Reset state safely when switching seeds and restore it when reconnecting.
- [ ] Add complete map markers for new check categories after obtaining event IDs.

## Complete standalone mode

- [x] Implement standalone graph traversal, seeded fill and sphere verification
      against the typed catalog, including fixed events and goals.
- [ ] Generate playable seeds from the complete real-game catalog, rather than
      the bundled logic example or only the combat-sticker shuffle.
- [ ] Include selected settings, starting inventory, catalog/version hashes and
      stable reward/check IDs in seed output; enforce them when applying patches.
- [ ] Deliver all local rewards and record checks without an Archipelago server.
- [ ] Make standalone gameplay fully functional without the RPC server.
      Optionally use RPC to run a local pseudo-Archipelago server so PopTracker
      can auto-track; this must remain optional for gameplay and local rewards.
- [ ] Package a reproducible standalone release with clear generation, patch,
      installation and launch instructions and no bundled copyrighted game data.

## Complete Archipelago 0.6.8 compatibility

- [x] Implement authenticated packet handling and reconnecting WebSocket transport.
- [x] Persist received indexes, pending items, checks and victory in SQLite,
      binding to seed/player/catalog/save; validate overlaps and replay gaps.
- [x] Implement direct offline local delivery and server-echo deduplication
      through an explicit atomic native-receipt adapter contract.
- [x] Verify transport against AP 0.6.8's actual wire serializer over WebSockets.
- [ ] Connect the runtime to verified native atomic delivery/receipt hooks.

- [x] Implement the AP world adapter for the shared logic example, with directed
      entrances, locked local fixed rewards, completion rules and slot output.
- [x] Validate the example AP archive and multiworld generation against 0.6.8.
- [ ] Replace demo item/location IDs with a permanent full-game ID registry;
      keep released IDs stable and reject unsupported catalog/seed versions.
- [ ] Implement all game settings as AP options and produce matching slot data,
      item classifications, item pools and access/completion rules.
- [ ] Build the actual AP network client for 0.6.8: connect/authenticate, report
      local checks, receive local and remote items, and report EndGoal completion.
- [ ] Use the RPC server in Archipelago mode to receive items from other worlds
      and send completed locations. Deliver local items directly without
      requiring RPC, including while the RPC connection is unavailable.
- [ ] Bridge that client to verified game reward/ability hooks; UDP memory reads
      alone do not implement game check detection or item delivery.
- [ ] Persist received-item indexes and pending deliveries; handle reconnects,
      duplicate packets, reloads and unavailable/full inventory without loss or
      duplicate rewards. Bind state to the correct seed, player and save.
- [ ] Preserve remote ownership in patch output and show meaningful remote
      reward information in the game/client where needed.
- [ ] Package the production `.apworld`, client, game patch and example YAML,
      and test a real multiworld session with Archipelago 0.6.8.

## Validation

- [x] Inspect experimental `.stickerpatch` files for ROM content or copyrighted
      game assets, then verify applying one to the user's ROM produces the mod.
- [x] Validate the combined seed-42 build: 651-byte asset-free recipe, 390
      shuffled pickups, 369 changed placements, preserved collection flags,
      unchanged bytes outside item pointers, tutorial files identical to the
      previously confirmed revision-2 patch. Thirty unit tests pass.
- [ ] Playtest the combined combat-shuffle/tutorial-skip mod in the emulator,
      including pickups and save/reload. Build checks alone do not establish this.
- [ ] Verify AP remote item receipt and location reporting through RPC, local
      item delivery without RPC, and standalone play with RPC disabled. Verify
      optional local pseudo-Archipelago RPC enables PopTracker auto-tracking.
- [ ] Test every reward kind and every event hook in the emulator.
- [ ] Test receiving an exit star from another world, receiving a Royal Sticker
      before its boss, and defeating a boss whose reward is a filler.
- [ ] Test every shop, locked drops, Secret Door ownership/place combinations,
      museum donations, banner settings, and save/load deduplication.
- [ ] Generate and independently solve seeds across supported settings.
- [ ] Complete full emulator playthroughs before calling the patch playable.
- [ ] Verify Decalburg can actually remain locked behind its item from the Menu
      starting region, with and without the production tutorial skip.
- [ ] Verify fixed events cannot be shuffled, both path directions use their
      respective rules, and victory requires completing the actual EndGoal.
- [ ] Complete standalone and AP runs through the same verified gameplay rules,
      including AP reconnection, remote delivery, save/reload and victory reports.

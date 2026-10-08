# Sticker Star randomizer

This specification records the requested replacement randomizer. The typed core,
standalone generator and Archipelago 0.6.8 logic example are implemented. Real
combat-sticker and tutorial-skip experiments exist; the full progression patch
and full Archipelago gameplay integration remain unfinished. The native runtime,
delivery mailbox, AP client and standalone tracking transport are implemented;
the authoritative catalog and gameplay validation remain outstanding.
The existing tracker rules are legacy placeholders and are not the new logic.

## Architecture and supported modes

Keep clean folders and subfolders separating typed domain classes, verified
game data, generation, ROM patching, emulator transport and AP integration.
Both standalone and Archipelago 0.6.8 must use the same authoritative catalog
and access rules, with a complete playable reward-delivery implementation.

Required classes and meanings:

- `Location`: where an item is received.
- `Item`: an identifiable reward.
- `Event`: a special item fixed at one specific location, never randomized.
- `Goal`: a special location with a specific fixed item, never randomized.
- `EndGoal`: a special Goal whose completion marks the randomizer won.
- `Region`: a group of locations with multiple possible paths.
- `Vector`: directed traversal with its own access rules.
- `Path`: a two-way connection with one vector in each direction; each vector
  has independent rules.
- `StartingRegion`: the one and only entirely open starting region, representing
  the main menu/map. Decalburg is separate and may be locked behind an item.
- `Rules`: requirements for accessing a location or traversing a vector.

These domain classes exist. Their use with the full real-game catalog, ability
hooks, persistent reward delivery and real victory event remains to be completed.

## Rewards

- Thing stickers unlock the corresponding Thing in the Thing shop.
- Six Royal Stickers, Hammer, and Paperization are shuffled progression items.
- Every mini star is a separate progression item. Receiving the 1-1 exit star
  opens 1-2 even if the reward was found somewhere else. Clearing a stage does
  not itself grant its exit star. Stages with multiple exits need separate IDs.
- Door sticker places are separate unlocks from the generic Secret Door sticker.
  Using a door requires its place unlock, Paperization, and a Secret Door sticker.
- Each generic sticker unlock gives one copy and unlocks that sticker in every
  shop. This includes Secret Door. Subsequent ordinary pickups of locked generic
  stickers become Kamek flip-flops. Randomized rewards bypass that conversion.
- Boss unlocks and scraps are separate progression items.
- Fillers are coins and sticker copies. Filler sticker copies still obey the
  locked-sticker conversion rule; they do not silently unlock their sticker.

## Sticker album pages

Setting `album_pages` has three planned modes:

- `all_at_start` (default): start with all eight pages, matching the old
  randomizer. There are no album-page rewards in the shuffled pool.
- `randomized`: retain the two base pages and shuffle six independent +1-page
  rewards into existing checks. They increase capacity, independently of Royal
  Stickers or boss victories. They do not create six extra check locations.
- `infinite`: experimental unlimited-capacity mode, subject to patch feasibility.
  It must not be implemented by simply overflowing the original page count.
  Investigate paged storage or an overflow inventory and save-format compatibility.
  No page rewards appear in this mode. Do not offer a playable infinite mode until
  inventory, placement, menus, battles, shops, and save/load are verified.

The base game starts with two pages and adds six upgrades, ending with eight:
https://www.mariowiki.com/Album_page

The tracker records the selected mode and the six received upgrades. It does not
change game capacity. In All at start mode the upgrades are irrelevant; in
Randomized mode available capacity is two plus the number of upgrades received.
Infinite mode is labeled experimental. Page capacity is not currently a hard
tracker access requirement: exact sticker sizes and simultaneous puzzle/battle
inventory requirements still need reconstruction from the game.

## Checks

- Each mini star, Thing pickup, Royal Sticker boss reward, and Kamek fight.
- The first victory against each enemy type, globally, not each spawn.
- Each success banner. Settings can remove these checks or divide each original
  requirement by ten (round up, minimum one).
- Each scrap pickup, the first conversation with each shop Toad, and each
  individual museum exhibit, including Thing exhibits.
- Check rewards are delivered once. Enemy, shop, and museum checks have stable
  IDs and persist in the save. Museum donation tracking is distinct from possession.

## Logic and generation

One catalog must define item IDs, check IDs, starting inventory, exits, and exact
access requirements. Both the seed generator and tracker must consume it.
Requirements use `all`, `any`, and counted item predicates. A seed is valid only
if all enabled checks and the configured goal can be reached by collecting its
rewards from the starting inventory. Banner settings affect the check pool before
filler allocation. A seed records its settings and catalog hash.

The core currently accepts a caller-supplied catalog and rejects unsupported
requirements and unknown references. No game catalog is asserted to be complete.
The old tracker's linear stage rules must not be used as an authoritative catalog.

## Remaining game integration

Identify the target game region/revision and emulator/console platform; obtain
game event IDs; verify every exit and puzzle requirement; enumerate doors, enemy
types, Kamek fights, shops, and banner thresholds. Implement reward hooks, ability
gates, boss gates, shop stock changes, pickup conversion, and persistent check
flags. Museum and Thing event IDs must be tied to actual game events.

Generated full-progression JSON files remain seed descriptions. The separate
experimental builders can produce actual LayeredFS overrides, and the Citra
transport can read/write memory, but these do not yet connect generated
progression seeds or AP items to complete in-game check/reward handling.

On 2026-10-08 the user validated the revised tutorial skip: arrival and Decalburg
unrolling work, the album contains four Jump/boot stickers, four Hammer stickers
and two Mushrooms, and normal movement resumes. This starting inventory is a
test fixture, not an exception to randomized Hammer or production starting rules.
See `PATCH_TODO.md` for the complete remaining implementation checklist.

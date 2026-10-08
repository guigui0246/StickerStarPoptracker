# Emulator patch TODO

Target: Azahar/Citra first. The supplied NCSD dump has primary title ID
`00040000000A5F00`, product code `CTR-P-AG5P`, and decrypted ExeFS/RomFS content
(verified directly, rather than inferred from the original NCCH flags).
Playable patch work needs decoded script/table formats and verified event mappings.
The typed domain, standalone engine, and Archipelago 0.6.8 example integration
are implemented; see `README.md` in this folder for their limits.

## Game inspection

- [ ] Record region, revision, title ID, and hashes of the user's own dump.
- [x] Inspect primary partition and enumerate 3,887 RomFS files and four ExeFS files.
- [x] Identify KSMR scripts and KDMR item/shop/map tables as investigation targets.
- [ ] Extract ExeFS/RomFS and identify event scripts, item tables, shop stock,
      inventory, ability flags, stage exits, museum records, and save flags.
- [ ] Identify a supported emulator mod-loading method and document installation.
- [ ] Reconstruct the complete check catalog with stable IDs: mini stars, Things,
      bosses, Kamek fights, first victory per enemy type, scraps, shop Toads,
      museum exhibits, and success banners with original thresholds.
- [ ] Map every mini-star reward to its exact exit, including alternate exits and
      shortcuts. Verify the tracker's provisional routes against game event IDs.
- [ ] Implement one door-place unlock per numbered level. The tracker now has
      all 38 items; map these IDs to game events and apply them to every actual
      door interaction. Towns have their own tracker maps and check groups.

## Reward hooks and persistence

- [ ] Replace vanilla rewards at all randomized checks; prevent double rewards.
- [ ] Grant Royal Stickers and mini stars without tying them to the source boss
      or stage. Open the destination encoded by the received star.
- [ ] Gate Hammer, Paperization, bosses, scraps, and door places by received items.
- [ ] Thing sticker rewards: grant one sticker and unlock the Thing shop entry.
- [ ] Generic sticker rewards: grant one copy and unlock the sticker in all shops.
- [ ] Convert locked ordinary sticker pickups (? blocks, enemy drops, etc.) into
      Kamek flip-flops; bypass conversion when receiving an unlock reward.
- [ ] Confirm filler-copy behavior and whether ordinary Thing sticker pickups
      need a separate conversion rule.
- [ ] Keep museum donation checks separate from sticker possession/shop unlocks.
- [ ] Persist collected checks and unlocks across saves, reloads, and emulator restarts.

## Settings and logic

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

- [ ] Load the seed's reward table into the patch; verify catalog/version hashes.
- [ ] Implement an emulator-to-PopTracker connection for received inventory and
      completed check flags, maintaining separate state for each.
- [ ] Reset state safely when switching seeds and restore it when reconnecting.
- [ ] Add complete map markers for new check categories after obtaining event IDs.

## Validation

- [ ] Test every reward kind and every event hook in the emulator.
- [ ] Test receiving an exit star from another world, receiving a Royal Sticker
      before its boss, and defeating a boss whose reward is a filler.
- [ ] Test every shop, locked drops, Secret Door ownership/place combinations,
      museum donations, banner settings, and save/load deduplication.
- [ ] Generate and independently solve seeds across supported settings.
- [ ] Complete full emulator playthroughs before calling the patch playable.

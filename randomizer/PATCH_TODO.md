# Emulator patch TODO

Target: Azahar/Citra first. No old randomizer files are available. Work on the
playable patch waits for a new game dump; tracker work can continue independently.

## Game inspection

- [ ] Record region, revision, title ID, and hashes of the user's own dump.
- [ ] Extract ExeFS/RomFS and identify event scripts, item tables, shop stock,
      inventory, ability flags, stage exits, museum records, and save flags.
- [ ] Identify a supported emulator mod-loading method and document installation.
- [ ] Reconstruct the complete check catalog with stable IDs: mini stars, Things,
      bosses, Kamek fights, first victory per enemy type, scraps, shop Toads,
      museum exhibits, and success banners with original thresholds.
- [ ] Map every mini-star reward to its exact exit, including alternate exits and
      shortcuts. Verify the tracker's provisional routes against game event IDs.
- [ ] Enumerate every door place separately. The tracker currently models only
      the existing 1-2 Secret Door check; it does not claim a complete door catalog.

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

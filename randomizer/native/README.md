# Native ARM patches

[`stickers-reference.S`](stickers-reference.S) contains the exact generated
assembly for the combined ability and sticker guard fixture. Four native
sticker entry points protect ordinary feasibility checks, forced additions,
named commits and direct album insertion. Unowned generic stickers become
Sandals; Things, pages and protected item kinds retain their original behavior.
17,760 isolated ARM executions using ROM-derived item descriptors verify these
guards, register preservation and bounded writes.

[`abilities-reference.S`](abilities-reference.S) is the exact assembly for the
validated `native-rpc-ability-v2` fixture. It contains raw ARM instruction words
with readable mnemonics, labels, addresses and a separate literal pool. Each
seed build generates its own `exefs/code.S` alongside `exefs/code.ips`;
ability-only builds also provide `exefs/abilities.S`.
Do not install the reference file's constants into another seed.

The executable hook replaces the accessory attachment function's first word
with a branch. The guard checks the persistent GF owner, initialized seed,
128-bit seed identity and Hammer/Paperization ownership before executing the
original attachment instructions. It preserves unrelated accessory bits and
uses existing executable padding; it does not enlarge an executable segment.

Most other changes run in Sticker Star's original KSM script VM. Checks,
inventory delivery, world-map admission, door and boss gates are compiled KSM
overrides, rather than ARM hooks. The ARM guard is necessary here because
vanilla accessory attachments can otherwise bypass script-owned abilities.

Sticker delivery first calls `item_try_addpouch(item, false)` to check capacity,
then calls it with `true` to insert the item. A successful feasibility check
alone does not change the album. Live native tests verify insertion, a full
album rejection followed by retry, save/reload persistence and network replay
without duplicate inventory. Hosts write only mailbox requests and save nonce.

The Python builder emits the same words directly so a separate ARM assembler
is not required. Assembly-to-IPS byte comparisons are regression checked, and
the executable behavior was tested in 384 isolated ARM executions.

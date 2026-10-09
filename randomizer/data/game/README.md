# Edit the game logic here

These Python modules contain the actual observed production registry: 497 item identities
and 416 checks. They contain identifiers and rules, not ROM bytes or game assets.

| File | What to edit |
| --- | --- |
| `items.py` | Named `Item` constants, names and progression classification. |
| `locations.py` | `Location` and fixed `EndGoal` objects with explicit `Rules`. |
| `regions.py` | Named `Region` objects and the sole `StartingRegion`. |
| `paths.py` | `Path` objects, each containing two independently ruled `Vector` objects. |
| `pool.py` | Typed `Item` objects to shuffle; one entry per non-fixed check. |
| `starting_items.py` | Typed precollected `Item` objects and physical starting copies. |
| `__init__.py` | Assemble and validate the authoring objects as a `GameDefinition`. |

The initial paths are **no-logic placeholders**, not a reviewed physical graph.
Replace the `...` Menu spokes with actual connections as you research
the game. Global enemy and museum checks need deliberate accessibility rules.
The default starting Jump is a **copy**, so it becomes a small slipper while
Jump is locked. The Jump **unlock** is in the shuffled pool.

Edit an actual location constructor, using named item and region constants:

```python
Location(
    "EXISTING_LOCATION_ID", "Check name", regions.ROOM_MAC_1_00.id,
    Rules.all_of(
        Rules.has(items.ABILITY_HAMMER.id),
        Rules.has(items.STICKER_UNLOCK_SL_JUMP.id),
    ),
)
```

`Rules.all_of()` means no requirement. Use `Rules.any_of(...)` for alternatives.
Requirements reference the typed constants in `items.py`. For physical links,
edit each `Vector`'s rules separately. Preserve the fixed Bowser `EndGoal` and
its victory reward. The initial paths use unconditional rules until you replace
them with reviewed physical connections.

The actual class definitions live in `randomizer/domain/`: `items.py` defines
`Item` and `Event`; `locations.py` defines `Location`, `Goal`, `EndGoal`;
`regions.py` defines `Region`, `StartingRegion`, `Path`, `Vector`; `rules.py`
defines `Rules`. `randomizer/data/example.py` demonstrates fixed `Event` and
`Goal` objects as well as separate directional requirements. The production
registry contains only the fixed milestones actually mapped to native sources;
do not invent story flags when adding native events.

Generate using your edits:

```text
python -m randomizer generate --logic catalog "ROM.3ds"
```

This directly loads the Python objects in this package, validates the native registry, refreshes
the logic digest in memory, fills the seed, builds the mod and exports the
matching tracker. You do not need to run a separate rebinding command. Use
`--catalog OTHER_DIRECTORY` still supports legacy JSON interchange catalogs. Use `--logic
no-logic` to rediscover sources from the ROM and ignore authored access rules.

`bindings.json` maps stable IDs to native sources/rewards. `native_reference.json`
is its original native contract, used only to validate bindings before applying
Python logic edits. Neither file supplies the current game logic. Leave these
two metadata files unchanged for ordinary logic work. Adding an actual
native source or reward requires updating the source mapper and binding contract.

An unlock authorizes only that exact sticker type and includes its first copy.
For example, `sticker_unlock/SL_W6_SANDAL_L` genuinely gives a Giant Slipper;
it is a valid shuffled reward, not a converted locked Jump. Subsequent copies of
an unlocked type keep their native identity; other locked types become the small
`SL_W6_SANDAL_S` slipper. A physical copy never unlocks its type.

See `docs/IMPLEMENTATION_GUIDE.md` at the repository root for architecture and
troubleshooting. The default map policy opens and shows ground routes/courses,
while stage admission still requires its access item. Boat/sky story handling
remains native; `--no-open-ground-routes` explicitly selects vanilla navigation.

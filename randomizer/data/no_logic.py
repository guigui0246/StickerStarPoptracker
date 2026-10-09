"""Build an explicit no-logic catalog from the observed production sources.

Unconditional tracker access describes no-logic mode, not proven physical
reachability. Native puzzles and admission gates still apply in the game.
"""

from ..domain import GameDefinition
from .catalog import Json, parse_catalog
from ..integrations.rom.native_delivery import ContainerReward, GoalBlockReward, NativeRewardKind, PeelReward, PickupReward
from ..integrations.rom.production_sources import ProductionSources, reward_id
from ..integrations.rom.native_generation import NativeBindings, NativeCheck


def check_region(check: NativeCheck) -> str:
    """Use real rooms where the source provides one; global checks stay global.

    Enemy type checks span encounters and cannot safely be assigned to their
    first script's room. Museum/banner flags similarly lack a physical room
    binding here. Authors can refine those groups without changing check IDs.
    """
    if isinstance(check, (ContainerReward, GoalBlockReward, PeelReward, PickupReward)):
        return "room/" + check.map_name
    script = getattr(check, "script_file", "")
    if isinstance(script, str) and script.startswith("Script/Map/"):
        return "room/" + script.rsplit("/", 1)[1].removesuffix(".bin")
    return "checks/" + check.id.split("/", 1)[0]


def build_no_logic_catalog(
    sources: ProductionSources, starting_stage: str | None = None, extra_starting: tuple[str, ...] = (),
) -> tuple[dict[str, Json], GameDefinition, NativeBindings]:
    """Include every observed check and every unique progression entitlement.

    Copies are filler, rather than a second entitlement. Starting tools, town,
    first course and a locked Jump copy avoid an empty bootstrap. No-logic
    deliberately does not promise a solvable placement of the remaining items.
    """
    rewards = {reward_id(reward): reward for reward in sources.rewards}
    if starting_stage is not None and "stage_access/" + starting_stage not in rewards:
        raise ValueError("Starting stage lacks an observed native admission capability")
    stage_starters = ("stage_access/" + starting_stage,) if starting_stage is not None else (
        "stage_access/A01", "stage_access/X00",
    )
    starting = [
        identifier for identifier in (
            "ability/hammer", "ability/paperization", *stage_starters, "sticker_copy/SL_JUMP",
        ) if identifier in rewards
    ]
    if len(set(extra_starting)) != len(extra_starting):
        raise ValueError("Starting reward overrides must have unique identities")
    for identifier in extra_starting:
        if identifier not in rewards or rewards[identifier].kind in {
            NativeRewardKind.VICTORY, NativeRewardKind.EVENT, NativeRewardKind.PAGE,
        }:
            raise ValueError("Starting overrides require an observed non-goal, non-page reward")
        if identifier not in starting:
            starting.append(identifier)
    victory = [check for check in sources.checks if check.reward.kind == NativeRewardKind.VICTORY]
    if len(victory) != 1 or "victory/1" not in rewards:
        raise ValueError("No-logic generation requires exactly one observed Bowser victory")
    pool = [
        identifier for identifier, reward in sorted(rewards.items())
        if identifier not in starting and reward.kind not in {
            NativeRewardKind.STICKER_COPY, NativeRewardKind.VICTORY, NativeRewardKind.EVENT, NativeRewardKind.PAGE,
            NativeRewardKind.COINS,
        }
    ]
    available = len(sources.checks) - 1
    if len(pool) > available:
        raise ValueError("Observed checks cannot hold every no-logic progression reward")
    if "coins/25" not in rewards:
        raise ValueError("No-logic generation requires the production coin filler")
    pool.extend(["coins/25"] * (available - len(pool)))
    # Include rooms without checks so a logic author can reconstruct traversal
    # without first extending the region registry. These paths are deliberately
    # no-logic Menu spokes; physical links require an independently authored graph.
    rooms = {"room/" + filename.rsplit("/", 1)[1].removesuffix(".bin") for filename in sources.source_hashes
             if filename.startswith("Script/Map/") and not filename.startswith("Script/Map/InterMission/")}
    regions = sorted({check_region(check) for check in sources.checks} | rooms)
    region_rows: list[Json] = [{"id": "menu", "name": "Menu", "starting": True}]
    region_rows.extend({"id": region, "name": region.replace("_", " ").title()} for region in regions)
    catalog: dict[str, Json] = {
        "format_version": 2,
        "items": [
            {"id": identifier, "name": identifier.replace("_", " "),
             "progression": reward.kind not in {NativeRewardKind.COINS, NativeRewardKind.STICKER_COPY}}
            for identifier, reward in sorted(rewards.items())
        ],
        "regions": region_rows,
        "locations": [
            {"id": check.id, "name": check.id.replace("_", " "), "region": check_region(check),
             **({"type": "end_goal", "item": "victory/1"} if check == victory[0] else {})}
            for check in sources.checks
        ],
        "paths": [
            {"id": "no_logic/" + region, "forward": {"source": "menu", "target": region},
             "reverse": {"source": region, "target": "menu"}}
            for region in regions
        ],
        "pool": list(pool),
        "starting_items": list(starting),
    }
    game = parse_catalog(catalog)
    return catalog, game, sources.bind(catalog)

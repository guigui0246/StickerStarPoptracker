"""Deterministic fill with graph reachability and automatic event collection."""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from random import Random
from ..domain import EndGoal, GameDefinition


@dataclass
class InventoryState:
    items: Counter[str]

    def count(self, item_id: str) -> int:
        return self.items[item_id]


@dataclass(frozen=True)
class Seed:
    seed: str
    placements: dict[str, str]
    spheres: tuple[tuple[str, ...], ...]
    won: bool


def reachable_regions(game: GameDefinition, inventory: InventoryState) -> set[str]:
    reached = {game.start.id}
    while True:
        before = len(reached)
        for path in game.paths:
            for vector in (path.forward, path.reverse):
                if vector.source in reached and vector.rules.allows(inventory):
                    reached.add(vector.target)
        if before == len(reached):
            return reached


def playthrough(game: GameDefinition, placements: Mapping[str, str]) -> Seed:
    fixed = game.fixed_rewards
    randomized = {loc.id for loc in game.locations} - fixed.keys()
    if set(placements) != randomized or Counter(placements.values()) != Counter(
        game.pool
    ):
        raise ValueError(
            "Placements must match the randomized locations and exact pool"
        )
    inventory = InventoryState(Counter(game.starting_items))
    remaining = {loc.id: loc for loc in game.locations}
    rewards = dict(placements) | fixed
    spheres: list[tuple[str, ...]] = []
    won = False
    while remaining:
        regions = reachable_regions(game, inventory)
        sphere = tuple(
            sorted(
                key
                for key, loc in remaining.items()
                if loc.region_id in regions and loc.rules.allows(inventory)
            )
        )
        if not sphere:
            break
        spheres.append(sphere)
        for key in sphere:
            inventory.items[rewards[key]] += 1
            won |= isinstance(remaining.pop(key), EndGoal)
    return Seed("", dict(placements), tuple(spheres), won)


def generate_seed(game: GameDefinition, seed: str | int, attempts: int = 200) -> Seed:
    if attempts < 1:
        raise ValueError("Attempts must be positive")
    rng = Random(str(seed))
    fixed = game.fixed_rewards
    items = {item.id: item for item in game.items}
    for _ in range(attempts):
        inventory = InventoryState(Counter(game.starting_items))
        remaining = {loc.id: loc for loc in game.locations}
        placements: dict[str, str] = {}
        progression = [item for item in game.pool if items[item].progression]
        filler = [item for item in game.pool if not items[item].progression]
        rng.shuffle(progression)
        for reward in progression:
            while True:
                regions = reachable_regions(game, inventory)
                events = [
                    key
                    for key, loc in remaining.items()
                    if key in fixed
                    and loc.region_id in regions
                    and loc.rules.allows(inventory)
                ]
                if not events:
                    break
                for key in events:
                    inventory.items[fixed[key]] += 1
                    del remaining[key]
            regions = reachable_regions(game, inventory)
            checks = [
                key
                for key, loc in remaining.items()
                if key not in fixed
                and loc.region_id in regions
                and loc.rules.allows(inventory)
            ]
            if not checks:
                break
            key = rng.choice(checks)
            placements[key] = reward
            del remaining[key]
            inventory.items[reward] += 1
        else:
            rng.shuffle(filler)
            for key, reward in zip(
                (key for key in remaining if key not in fixed), filler, strict=True
            ):
                placements[key] = reward
            result = playthrough(game, placements)
            if result.won and sum(map(len, result.spheres)) == len(game.locations):
                return Seed(str(seed), placements, result.spheres, True)
    raise ValueError("No fully reachable seed found within the attempt limit")

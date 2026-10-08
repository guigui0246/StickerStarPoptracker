from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Self
from .catalog import JsonObject, KINDS


@dataclass
class RewardState:
    inventory: Counter[str] = field(default_factory=Counter[str])
    sticker_inventory: Counter[str] = field(default_factory=Counter[str])
    generic_unlocks: set[str] = field(default_factory=set[str])
    thing_shop_unlocks: set[str] = field(default_factory=set[str])
    completed_checks: set[str] = field(default_factory=set[str])
    coins: int = 0

    def ordinary_sticker(self, sticker: str) -> str:
        delivered = sticker if sticker in self.generic_unlocks else "kamek_flip_flop"
        self.sticker_inventory[delivered] += 1
        return delivered

    def deliver(
        self, check_id: str, reward_id: str, items: Mapping[str, JsonObject]
    ) -> bool:
        if check_id in self.completed_checks:
            return False
        reward = items[reward_id]
        kind = reward["kind"]
        if kind not in KINDS:
            raise ValueError(f"Unsupported reward kind: {kind}")
        if kind == "generic_sticker":
            self.generic_unlocks.add(reward["sticker"])
            self.sticker_inventory[reward["sticker"]] += 1
        elif kind == "thing":
            self.thing_shop_unlocks.add(reward["sticker"])
            self.sticker_inventory[reward["sticker"]] += 1
        elif kind == "sticker_copy":
            self.ordinary_sticker(reward["sticker"])
        elif kind == "coins":
            self.coins += reward["amount"]
        self.inventory[reward_id] += 1
        self.completed_checks.add(check_id)
        return True

    def shop_sells(self, sticker: str, thing: bool = False) -> bool:
        return sticker in (self.thing_shop_unlocks if thing else self.generic_unlocks)

    def to_save(self) -> JsonObject:
        return {
            "inventory": dict(self.inventory),
            "sticker_inventory": dict(self.sticker_inventory),
            "generic_unlocks": sorted(self.generic_unlocks),
            "thing_shop_unlocks": sorted(self.thing_shop_unlocks),
            "completed_checks": sorted(self.completed_checks),
            "coins": self.coins,
        }

    @classmethod
    def from_save(cls, data: JsonObject) -> Self:
        return cls(
            Counter(data["inventory"]),
            Counter(data["sticker_inventory"]),
            set(data["generic_unlocks"]),
            set(data["thing_shop_unlocks"]),
            set(data["completed_checks"]),
            data["coins"],
        )

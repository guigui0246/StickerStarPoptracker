"""Immutable, composable access requirements shared by both backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


class Inventory(Protocol):
    def count(self, item_id: str) -> int: ...


@dataclass(frozen=True)
class Rules:
    operator: Literal["all", "any", "item"] = "all"
    children: tuple[Rules, ...] = ()
    item_id: str = ""
    amount: int = 1

    def __post_init__(self) -> None:
        if self.operator not in {"all", "any", "item"}:
            raise ValueError("Unknown rule operator")
        if self.operator == "item":
            if (
                not self.item_id
                or type(self.amount) is not int
                or self.amount < 1
                or self.children
            ):
                raise ValueError(
                    "Item rules need an ID, a positive count, and no children"
                )
        elif self.item_id or self.amount != 1:
            raise ValueError("Composite rules cannot contain an item predicate")

    @classmethod
    def has(cls, item_id: str, amount: int = 1) -> Rules:
        return cls("item", item_id=item_id, amount=amount)

    @classmethod
    def all_of(cls, *children: Rules) -> Rules:
        return cls("all", children)

    @classmethod
    def any_of(cls, *children: Rules) -> Rules:
        return cls("any", children)

    def allows(self, inventory: Inventory) -> bool:
        if self.operator == "item":
            return inventory.count(self.item_id) >= self.amount
        values = (child.allows(inventory) for child in self.children)
        return all(values) if self.operator == "all" else any(values)

    def referenced_items(self) -> frozenset[str]:
        if self.operator == "item":
            return frozenset((self.item_id,))
        return frozenset().union(*(child.referenced_items() for child in self.children))

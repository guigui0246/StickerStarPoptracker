"""Random checks and fixed milestone checks."""

from dataclasses import dataclass
from .items import Item
from .rules import Rules


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    region_id: str
    rules: Rules = Rules()


@dataclass(frozen=True)
class Goal(Location):
    """A location with a specific reward that never enters the fill pool."""

    item: Item = Item("goal", "Goal")


@dataclass(frozen=True)
class EndGoal(Goal):
    """Collecting this location's fixed reward wins the seed."""

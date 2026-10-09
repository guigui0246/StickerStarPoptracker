"""Authoritative typed Python game definition; JSON is only an interchange format."""

from ...domain import GameDefinition
from .items import ITEMS
from .locations import LOCATIONS
from .paths import PATHS
from .pool import POOL
from .regions import REGIONS
from .starting_items import STARTING_ITEMS


def game_definition() -> GameDefinition:
    """Assemble and validate the exact objects authored in this package."""
    return GameDefinition(
        items=ITEMS, regions=REGIONS, locations=LOCATIONS, paths=PATHS,
        pool=tuple(item.id for item in POOL),
        starting_items=tuple(item.id for item in STARTING_ITEMS),
    )

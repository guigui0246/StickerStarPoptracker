from ..domain import (
    EndGoal,
    Event,
    GameDefinition,
    Goal,
    Item,
    Location,
    Path,
    Region,
    Rules,
    StartingRegion,
    Vector,
)


def example_game() -> GameDefinition:
    """Small runnable graph demonstrating locked Decalburg and local milestones."""
    town = Item("decalburg_access", "Decalburg Access")
    hammer = Item("hammer", "Hammer")
    coins = Item("coins", "20 Coins", False)
    event = Event("toad_rescued", "Toad Rescued", location_id="rescue")
    royal = Item("royal", "Royal Sticker")
    victory = Item("victory", "Victory")
    return GameDefinition(
        items=(town, hammer, coins, event, royal, victory),
        regions=(
            StartingRegion("map", "Menu"),
            Region("town", "Decalburg"),
            Region("field", "World 1-1"),
        ),
        locations=(
            Location("map_gift", "Map Gift", "map"),
            Location("field_pickup", "Field Pickup", "field"),
            Location("town_gift", "Town Gift", "town"),
            Location("rescue", "Rescue Toad", "field", Rules.has("hammer")),
            Goal(
                "boss", "Defeat Example Boss", "field", Rules.has("toad_rescued"), royal
            ),
            EndGoal("end", "Example Victory", "town", Rules.has("royal"), victory),
        ),
        paths=(
            Path(
                "town_path",
                Vector("map", "town", Rules.has("decalburg_access")),
                Vector("town", "map"),
            ),
            Path(
                "field_path",
                Vector("map", "field"),
                Vector("field", "map", Rules.has("hammer")),
            ),
        ),
        pool=(town.id, hammer.id, coins.id),
    )

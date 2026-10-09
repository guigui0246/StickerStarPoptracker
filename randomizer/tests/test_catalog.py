from typing import Any, cast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ..data.catalog import load_catalog, parse_rules
from ..domain import EndGoal, StartingRegion
from ..standalone import generate_seed


class CatalogTests(unittest.TestCase):
    def test_typed_catalog_generation(self) -> None:
        data = {
            "format_version": 2,
            "items": [
                {"id": "hammer", "name": "Hammer"},
                {"id": "victory", "name": "Victory"},
            ],
            "regions": [{"id": "menu", "name": "Menu", "starting": True}],
            "locations": [
                {"id": "gift", "name": "Gift", "region": "menu"},
                {
                    "id": "end",
                    "name": "Win",
                    "region": "menu",
                    "type": "end_goal",
                    "item": "victory",
                    "requires": {"item": "hammer"},
                },
            ],
            "paths": [],
            "pool": ["hammer"],
        }
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as directory:
            target = Path(directory) / "catalog.json"
            target.write_text(json.dumps(data), encoding="utf-8")
            game = load_catalog(target)
        self.assertIsInstance(game.start, StartingRegion)
        self.assertIsInstance(game.locations[1], EndGoal)
        self.assertTrue(generate_seed(game, 1).won)

    def test_malformed_rules_fail_at_boundary(self) -> None:
        for rule in (
            {"item": "hammer", "all": []},
            {"count": ["hammer", True]},
            {"count": ["hammer", 0]},
            {"any": "hammer"},
            {"unknown": []},
        ):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                parse_rules(cast(Any, rule))


if __name__ == "__main__":
    unittest.main()

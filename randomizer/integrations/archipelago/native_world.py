"""AP 0.6.8 generation using the shared catalog and native patch recipes."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import cast

from BaseClasses import Item as APItem, Location as APLocation
from Options import Choice

from ...settings import AlbumPages, Banners, Settings
from ..rom.mailbox import RemoteReward, RemoteSession
from ..rom.native_delivery import BannerReward, DeliveryPlan, NativeReward, NativeRewardKind
from ..rom.native_generation import NativeBindings, configure_catalog
from ..rom.native_recipe import NativeRecipe
from .native_catalog import NativeAPCatalog
from .world import SharedCatalogWorld, StickerStarOptions

GAME_NAME = "Paper Mario: Sticker Star (Native Catalog)"


class NativeAlbumPages(Choice):
    """Start with eight pages, or shuffle six upgrades into existing checks."""
    display_name = "Sticker album pages"
    option_all_at_start = 0
    option_randomized = 1
    default = 0


class NativeBanners(Choice):
    """Original success banners, rounded one-tenth thresholds, or no banners."""
    display_name = "Success banners"
    option_original = 0
    option_reduced = 1
    option_off = 2
    default = 0


@dataclass
class NativeStickerStarOptions(StickerStarOptions):
    album_pages: NativeAlbumPages
    banners: NativeBanners


class NativeStickerStarItem(APItem):
    game = GAME_NAME


class NativeStickerStarLocation(APLocation):
    game = GAME_NAME


def create_native_world(catalog: NativeAPCatalog) -> type[SharedCatalogWorld]:
    """Register one packaged catalog; its registry persists between revisions."""
    fixed = set(catalog.game.fixed_rewards.values())

    class NativeStickerStarWorld(SharedCatalogWorld):
        game = GAME_NAME
        definition = catalog.game
        bindings: NativeBindings = catalog.bindings
        item_type = NativeStickerStarItem
        location_type = NativeStickerStarLocation
        options_dataclass = NativeStickerStarOptions
        options: NativeStickerStarOptions
        item_name_to_id = {item.name: catalog.registry.items[item.id] for item in catalog.game.items if item.id not in fixed}
        location_name_to_id = {location.name: catalog.registry.locations[location.id] for location in catalog.game.locations if location.id not in catalog.game.fixed_rewards}
        origin_region_name = catalog.game.start.name
        native_settings: Settings

        def generate_early(self) -> None:
            self.native_settings = Settings((AlbumPages.ALL_AT_START, AlbumPages.RANDOMIZED)[self.options.album_pages.value],
                                     (Banners.ORIGINAL, Banners.REDUCED, Banners.OFF)[self.options.banners.value])
            self.definition, self.bindings = configure_catalog(catalog.game, catalog.bindings, self.native_settings)

        def get_filler_item_name(self) -> str:
            names = sorted(item.name for item in self.definition.items if not item.progression and self.bindings.items[item.id].kind in {NativeRewardKind.COINS, NativeRewardKind.STICKER_COPY})
            if not names:
                raise ValueError("This catalog has no filler for AP pool replacement")
            return names[0]

        def fill_slot_data(self) -> dict[str, object]:
            from .tracker_catalog import TrackerCatalog
            return {"format_version": 1, "catalog_hash": catalog.catalog_hash,
                    "native_catalog": True, "full_game_catalog": False,
                    "settings": self.native_settings.to_json(),
                    "tracker": TrackerCatalog(self.definition, catalog.registry, catalog.catalog_hash).mappings()}

        def native_plan(self) -> DeliveryPlan:
            items = {item.name: item.id for item in self.definition.items}
            precollected = self.multiworld.precollected_items[self.player]
            starting_ids = tuple(catalog.registry.items[items[item.name]] for item in precollected)
            starting = tuple(self.bindings.items[items[item.name]] for item in precollected)
            available = set(self.definition.pool) | {items[item.name] for item in precollected}
            selectors = tuple(RemoteReward(catalog.registry.items[identifier], self.bindings.items[identifier]) for identifier in sorted(available))
            checks = []
            for location in self.definition.locations:
                source = self.bindings.locations[location.id]
                if isinstance(source, BannerReward):
                    source = replace(source, mode=self.native_settings.banners)
                fixed_item = self.definition.fixed_rewards.get(location.id)
                if fixed_item is not None:
                    reward = self.bindings.items[fixed_item]
                else:
                    placed = self.multiworld.get_location(location.name, self.player).item
                    if placed is None:
                        raise ValueError(f"AP has not filled {location.name}")
                    reward = self.bindings.items[items[placed.name]] if placed.player == self.player else NativeReward(NativeRewardKind.REMOTE, placed.player)
                checks.append(replace(source, reward=reward))
            royals = any(entry.reward.kind == NativeRewardKind.ROYAL for entry in selectors)
            session = RemoteSession(self.multiworld.seed_name, 0, self.player, catalog.catalog_hash)
            plan = DeliveryPlan(tuple(checks), self.native_settings.album_pages, royals, selectors, session,
                                catalog.sticker_policy, seed_name=session.seed, starting_rewards=starting,
                                starting_item_ids=starting_ids)
            from ..rom.mailbox import fit_mailbox
            return fit_mailbox(plan)

        def generate_output(self, output_directory: str) -> None:
            from .tracker_catalog import TrackerCatalog
            plan = self.native_plan()
            stem = Path(output_directory) / self.multiworld.get_out_file_name_base(self.player)
            stem.parent.mkdir(parents=True, exist_ok=True)
            recipe = NativeRecipe(self.multiworld.seed_name, catalog.rom_sha256, plan)
            Path(str(stem) + ".stickerpatch").write_bytes(recipe.encode())
            locations = {self.bindings.locations[location.id].id: catalog.registry.locations[location.id]
                         for location in self.definition.locations if location.id not in self.definition.fixed_rewards}
            local = []
            remote = {}
            for location in self.definition.locations:
                if location.id in self.definition.fixed_rewards:
                    continue
                placed = self.multiworld.get_location(location.name, self.player).item
                assert placed is not None
                if placed.player == self.player:
                    local.append({"class": "NetworkItem", "item": cast(int, placed.code),
                                  "location": catalog.registry.locations[location.id], "player": self.player,
                                  "flags": placed.flags})
                else:
                    remote[self.bindings.locations[location.id].id] = {"item": placed.name, "player": placed.player,
                        "player_name": self.multiworld.player_name[placed.player], "location_name": location.name}
            Path(str(stem) + ".client.json").write_text(json.dumps({"format_version": 1, "game": self.game,
                "name": self.multiworld.player_name[self.player], "seed": self.multiworld.seed_name,
                "catalog_hash": catalog.catalog_hash, "locations": locations, "local_rewards": local, "remote_placements": remote,
                "settings": self.native_settings.to_json(), "save_seed_fingerprint": plan.fingerprint.hex()}, indent=2) + "\n", encoding="utf-8")
            tracker = TrackerCatalog(self.definition, catalog.registry, catalog.catalog_hash)
            Path(str(stem) + ".tracker.lua").write_text(tracker.lua(), encoding="utf-8")
            Path(str(stem) + ".tracker.json").write_text(json.dumps(tracker.definitions(), indent=2) + "\n", encoding="utf-8")
            Path(str(stem) + ".tracker-data.json").write_text(json.dumps(tracker.data_package(), indent=2) + "\n", encoding="utf-8")

    return NativeStickerStarWorld

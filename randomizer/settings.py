"""Shared settings boundary for seeds, patches and client slot data."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class AlbumPages(str, Enum):
    VANILLA = "vanilla"
    ALL_AT_START = "all_at_start"
    RANDOMIZED = "randomized"
    INFINITE = "infinite"


class Banners(str, Enum):
    ORIGINAL = "original"
    REDUCED = "reduced"
    OFF = "off"


class Museum(str, Enum):
    ALL = "all"
    OFF = "off"
    NORMAL = "normal"
    THINGS = "things"


class EnemyRewards(str, Enum):
    ON = "on"
    OFF = "off"


class DoorStickers(str, Enum):
    RANDOMIZED = "randomized"
    VANILLA = "vanilla"


class GenericStickers(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Settings:
    album_pages: AlbumPages = AlbumPages.ALL_AT_START
    banners: Banners = Banners.ORIGINAL
    museum: Museum = Museum.ALL
    enemy_rewards: EnemyRewards = EnemyRewards.ON
    door_stickers: DoorStickers = DoorStickers.RANDOMIZED
    generic_stickers: GenericStickers = GenericStickers.ENABLED

    def __post_init__(self) -> None:
        if not isinstance(self.album_pages, AlbumPages) or not isinstance(self.banners, Banners):
            raise ValueError("Settings require supported enum values")
        if self.album_pages == AlbumPages.INFINITE:
            raise ValueError("Infinite inventory is not safe to enable before storage and save-format verification")
        if not isinstance(self.museum, Museum) or not isinstance(self.enemy_rewards, EnemyRewards):
            raise ValueError("Settings require supported museum and enemy reward modes")
        if not isinstance(self.door_stickers, DoorStickers):
            raise ValueError("Settings require a supported door sticker mode")
        if not isinstance(self.generic_stickers, GenericStickers):
            raise ValueError("Settings require a supported generic sticker mode")

    def banner_threshold(self, original: int) -> int | None:
        if type(original) is not int or original < 1:
            raise ValueError("Banner thresholds must be positive integers")
        if self.banners == Banners.OFF:
            return None
        return max(1, (original + 9) // 10) if self.banners == Banners.REDUCED else original

    def to_json(self) -> dict[str, str]:
        result = {"album_pages": self.album_pages.value, "banners": self.banners.value}
        # Preserve old seed/tracker settings at their defaults. New policies are
        # explicit when selected, so old recipes remain decodable and comparable.
        for key, value, default in (
            ("museum", self.museum, Museum.ALL), ("enemy_rewards", self.enemy_rewards, EnemyRewards.ON),
            ("door_stickers", self.door_stickers, DoorStickers.RANDOMIZED),
            ("generic_stickers", self.generic_stickers, GenericStickers.ENABLED),
        ):
            if value != default:
                result[key] = value.value
        return result

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "Settings":
        required = {"album_pages", "banners"}
        if not required <= data.keys() <= required | {"museum", "enemy_rewards", "door_stickers", "generic_stickers"}:
            raise ValueError("Settings require album_pages and banners")
        album, banners = data["album_pages"], data["banners"]
        if not isinstance(album, str) or not isinstance(banners, str):
            raise ValueError("Setting values must be strings")
        if any(not isinstance(value, str) for value in data.values()):
            raise ValueError("Setting values must be strings")
        return cls(
            AlbumPages(album), Banners(banners), Museum(str(data.get("museum", "all"))),
            EnemyRewards(str(data.get("enemy_rewards", "on"))), DoorStickers(str(data.get("door_stickers", "randomized"))),
            GenericStickers(str(data.get("generic_stickers", "enabled"))),
        )

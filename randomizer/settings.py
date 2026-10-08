"""Shared settings boundary for seeds, patches and client slot data."""

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class AlbumPages(str, Enum):
    ALL_AT_START = "all_at_start"
    RANDOMIZED = "randomized"
    INFINITE = "infinite"


class Banners(str, Enum):
    ORIGINAL = "original"
    REDUCED = "reduced"
    OFF = "off"


@dataclass(frozen=True)
class Settings:
    album_pages: AlbumPages = AlbumPages.ALL_AT_START
    banners: Banners = Banners.ORIGINAL

    def __post_init__(self) -> None:
        if not isinstance(self.album_pages, AlbumPages) or not isinstance(self.banners, Banners):
            raise ValueError("Settings require supported enum values")
        if self.album_pages == AlbumPages.INFINITE:
            raise ValueError("Infinite inventory is not safe to enable before storage and save-format verification")

    def banner_threshold(self, original: int) -> int | None:
        if type(original) is not int or original < 1:
            raise ValueError("Banner thresholds must be positive integers")
        if self.banners == Banners.OFF:
            return None
        return max(1, (original + 9) // 10) if self.banners == Banners.REDUCED else original

    def to_json(self) -> dict[str, str]:
        return {"album_pages": self.album_pages.value, "banners": self.banners.value}

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> "Settings":
        if set(data) != {"album_pages", "banners"}:
            raise ValueError("Settings require album_pages and banners")
        album, banners = data["album_pages"], data["banners"]
        if not isinstance(album, str) or not isinstance(banners, str):
            raise ValueError("Setting values must be strings")
        return cls(AlbumPages(album), Banners(banners))

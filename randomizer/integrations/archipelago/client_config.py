"""Strict client configuration emitted alongside native AP patch recipes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import TYPE_CHECKING

from ...data.catalog import Json, array, obj, string
from ...settings import Settings
from .runtime import ReceivedItem, integer

if TYPE_CHECKING:
    from ..citra.native import NativeProfile


@dataclass(frozen=True)
class RemotePlacement:
    item: str
    player: int
    player_name: str
    location_name: str

    @classmethod
    def parse(cls, value: Json) -> "RemotePlacement":
        data = obj(value)
        if set(data) != {"item", "player", "player_name", "location_name"}:
            raise ValueError("Unsupported remote placement description")
        result = cls(string(data["item"]), integer(data["player"]), string(data["player_name"]), string(data["location_name"]))
        if result.player < 1 or any(not text or len(text) > 1024 for text in (result.item, result.player_name, result.location_name)):
            raise ValueError("Invalid remote placement description")
        return result


@dataclass(frozen=True)
class NativeClientConfig:
    game: str
    name: str
    seed: str
    catalog_hash: str
    fingerprint: bytes
    locations: dict[str, int]
    local_rewards: tuple[ReceivedItem, ...]
    settings: Settings
    remote_placements: dict[str, RemotePlacement] = field(default_factory=dict)

    @classmethod
    def parse(cls, value: Json) -> "NativeClientConfig":
        data = obj(value)
        fields = {"format_version", "game", "name", "seed", "catalog_hash", "save_seed_fingerprint", "locations", "local_rewards", "settings"}
        if not fields <= set(data) <= fields | {"remote_placements"} or type(data["format_version"]) is not int or data["format_version"] != 1:
            raise ValueError("Unsupported native client configuration")
        fingerprint = bytes.fromhex(string(data["save_seed_fingerprint"]))
        catalog_hash = string(data["catalog_hash"])
        if len(fingerprint) != 16 or len(catalog_hash) != 64 or any(character not in "0123456789abcdef" for character in catalog_hash):
            raise ValueError("Invalid client seed/catalog identity")
        locations = {identifier: integer(value) for identifier, value in obj(data["locations"]).items()}
        if any(value < 1 for value in locations.values()) or len(set(locations.values())) != len(locations):
            raise ValueError("Ambiguous native/AP location registry")
        local = tuple(ReceivedItem.parse(raw) for raw in array(data["local_rewards"]))
        if len({item.location for item in local}) != len(local) or any(item.location not in locations.values() for item in local):
            raise ValueError("Local placements require distinct mapped locations")
        settings = Settings.from_json(obj(data["settings"]))
        remote = {key: RemotePlacement.parse(raw) for key, raw in obj(data.get("remote_placements", {})).items()}
        if set(remote) - locations.keys() or {locations[key] for key in remote} & {item.location for item in local}:
            raise ValueError("Remote descriptions overlap local or unknown placements")
        return cls(string(data["game"]), string(data["name"]), string(data["seed"]), catalog_hash,
                   fingerprint, locations, local, settings, remote)

    @classmethod
    def load(cls, path: Path) -> "NativeClientConfig":
        from ..rom.seed_patch import unique_object
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Native client configuration exceeds the supported size")
        value: Json = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        return cls.parse(value)

    def validate(self, profile: NativeProfile) -> None:
        session = profile.session
        if (self.seed, self.catalog_hash, self.fingerprint) != (session.seed, session.catalog_hash, profile.fingerprint):
            raise ValueError("Client configuration belongs to a different installed seed")
        if set(self.locations) - profile.checks.keys():
            raise ValueError("Client configuration names an unknown native check")
        native_ids = {value: key for key, value in self.locations.items()}
        for item in self.local_rewards:
            if item.player != session.slot or profile.selector_rewards.get(item.item) != profile.check_rewards[native_ids[item.location]]:
                raise ValueError("Local client reward does not match the installed native placement")
        for identifier, entry in self.remote_placements.items():
            from ..rom.native_delivery import NativeRewardKind
            native = profile.check_rewards[identifier]
            if entry.player == session.slot or native.kind != NativeRewardKind.REMOTE or native.value != entry.player:
                raise ValueError("Remote description does not match the installed owner")

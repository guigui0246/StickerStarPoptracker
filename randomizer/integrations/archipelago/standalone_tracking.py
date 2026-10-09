"""Read-only native tracking, including committed starting rewards and rollback."""

from ...data.catalog import Json, array, obj
from ..citra.native import NativeGame, NativeProfile
from ..rom.plan_io import reward
from .runtime import ReceivedItem, integer
from .tracker_server import TrackingSnapshot


class StandaloneObservation:
    def __init__(self, config: Json, profile: NativeProfile, game: NativeGame, report: Json) -> None:
        data = obj(config)
        if (
            set(data)
            != {"format_version", "seed", "catalog_hash", "save_seed_fingerprint", "locations", "rewards", "starting"}
            or type(data["format_version"]) is not int
            or data["format_version"] != 1
        ):
            raise ValueError("Unsupported standalone tracking configuration")
        if (data["seed"], data["catalog_hash"], data["save_seed_fingerprint"]) != (
            profile.session.seed,
            profile.session.catalog_hash,
            profile.fingerprint.hex(),
        ):
            raise ValueError("Tracking configuration belongs to another seed")
        self.locations = {key: integer(value) for key, value in obj(data["locations"]).items()}
        if (
            set(self.locations) - profile.checks.keys()
            or {location: profile.checks[key] for key, location in self.locations.items()} != game.locations
        ):
            raise ValueError("Tracking locations do not match the native adapter")
        self.rewards: dict[str, ReceivedItem] = {}
        for key, raw in obj(data["rewards"]).items():
            entry = obj(raw)
            if (
                set(entry) != {"item", "reward"}
                or key not in self.locations
                or reward(entry["reward"]) != profile.check_rewards[key]
            ):
                raise ValueError("Tracking placement differs from the native reward")
            self.rewards[key] = ReceivedItem(integer(entry["item"]), self.locations[key], 1, 0)
        if set(self.rewards) != set(self.locations):
            raise ValueError("Tracking requires every randomized placement")
        self.starting: dict[str, ReceivedItem] = {}
        starters = array(data["starting"])
        native_starters = array(obj(report).get("starting_rewards"))
        if len(starters) != len(native_starters):
            raise ValueError("Starting tracking rewards differ from the installed patch")
        for index, (raw, native) in enumerate(zip(starters, native_starters, strict=True)):
            entry = obj(raw)
            if set(entry) != {"item", "reward"} or reward(entry["reward"]) != reward(native):
                raise ValueError("Starting tracking reward differs from the native reward")
            flag = f"gf_rando_starting_{index:04d}"
            if flag not in profile.flags:
                raise ValueError("Starting reward has no native receipt")
            self.starting[flag] = ReceivedItem(integer(entry["item"]), -2, 1, 0)
        self.profile, self.game = profile, game
        self.order: list[str] = []

    def snapshot(self) -> TrackingSnapshot:
        self.game.verify_executable()
        _, flags = self.game.snapshot()
        collected = {location for location, check in self.game.locations.items() if self.game.bit(flags, check.collected)}
        receipts = set()
        for key in self.rewards:
            delivered = self.profile.checks[key].delivered
            if delivered is not None and self.game.bit(flags, delivered):
                receipts.add(key)
        receipts.update(key for key in self.starting if self.game.bit(flags, self.profile.flags[key]))
        if not set(self.order) <= receipts:
            self.order.clear()
        self.order.extend(sorted(receipts - set(self.order)))
        items = self.rewards | self.starting
        victory = self.profile.flags.get("gf_rando_victory")
        return TrackingSnapshot(
            tuple(sorted(collected)),
            tuple(items[key] for key in self.order),
            victory is not None and self.game.bit(flags, victory),
        )

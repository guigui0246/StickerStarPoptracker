"""Strict asset-free serialization for native check/reward plans."""

from dataclasses import asdict
import json
from pathlib import Path

from ...data.catalog import Json, array, obj, string
from ...settings import AlbumPages, Banners
from .mailbox import RemoteReward, RemoteSession
from .native_delivery import BannerReward, DeliveryPlan, EnemyReward, FlagReward, GoalBlockReward, NativeReward, NativeRewardKind, PickupReward, ScriptReward
from .stickers import StickerPolicy


def integer(value: Json) -> int:
    if type(value) is not int:
        raise ValueError("Expected an integer")
    return value


def boolean(value: Json) -> bool:
    if type(value) is not bool:
        raise ValueError("Expected a boolean native setting")
    return value


def reward(value: Json) -> NativeReward:
    row = obj(value)
    if set(row) != {"kind", "value"}:
        raise ValueError("Native rewards require kind and value")
    native_value = row["value"]
    if not isinstance(native_value, str) and type(native_value) is not int:
        raise ValueError("Invalid native reward value")
    return NativeReward(NativeRewardKind(string(row["kind"])), native_value)


def checks(value: Json) -> tuple[GoalBlockReward | PickupReward | FlagReward | BannerReward | ScriptReward | EnemyReward, ...]:
    result: list[GoalBlockReward | PickupReward | FlagReward | BannerReward | ScriptReward | EnemyReward] = []
    for raw in array(value):
        row = obj(raw)
        native = reward(row.get("reward"))
        fields = set(row)
        if fields == {"map_name", "source_flag", "reward"}:
            result.append(GoalBlockReward(string(row["map_name"]), string(row["source_flag"]), native))
        elif fields == {"map_name", "object_name", "source_item", "reward"}:
            result.append(PickupReward(string(row["map_name"]), string(row["object_name"]), string(row["source_item"]), native))
        elif fields == {"category", "source_flag", "reward"}:
            result.append(FlagReward(string(row["category"]), string(row["source_flag"]), native))
        elif fields == {"honor", "mode", "reward"}:
            result.append(BannerReward(string(row["honor"]), Banners(string(row["mode"])), native))
        elif fields == {"category", "script_file", "function", "reward"}:
            result.append(ScriptReward(string(row["category"]), string(row["script_file"]), string(row["function"]), native))
        elif fields == {"unit_id", "script_file", "function", "reward"}:
            result.append(EnemyReward(string(row["unit_id"]), string(row["script_file"]), string(row["function"]), native))
        else:
            raise ValueError("Unsupported native check fields")
    return tuple(result)


def decode_plan(value: Json) -> DeliveryPlan:
    row = obj(value)
    if set(row) != {"checks", "album_pages", "shuffle_royals", "remote_rewards", "remote_session", "sticker_policy", "skip_opening", "skip_dialogue", "seed_name"}:
        raise ValueError("Unsupported native plan fields")
    if any(type(row[key]) is not bool for key in ("shuffle_royals", "skip_opening", "skip_dialogue")):
        raise ValueError("Native settings must be boolean")
    remote = []
    for raw in array(row["remote_rewards"]):
        entry = obj(raw)
        if set(entry) != {"item_id", "reward"}:
            raise ValueError("Invalid remote selector fields")
        remote.append(RemoteReward(integer(entry["item_id"]), reward(entry["reward"])))
    session = None
    if row["remote_session"] is not None:
        entry = obj(row["remote_session"])
        if set(entry) != {"seed", "team", "slot", "catalog_hash"}:
            raise ValueError("Invalid remote session fields")
        session = RemoteSession(string(entry["seed"]), integer(entry["team"]), integer(entry["slot"]), string(entry["catalog_hash"]))
    policy = None
    if row["sticker_policy"] is not None:
        entry = obj(row["sticker_policy"])
        if set(entry) != {"generic", "things", "replacement"}:
            raise ValueError("Invalid sticker policy fields")
        things = []
        for raw in array(entry["things"]):
            pair = array(raw)
            if len(pair) != 2:
                raise ValueError("Expected sticker/Thing pair")
            things.append((string(pair[0]), string(pair[1])))
        policy = StickerPolicy(tuple(string(item) for item in array(entry["generic"])), tuple(things), string(entry["replacement"]))
    pages = AlbumPages(string(row["album_pages"])) if row["album_pages"] is not None else None
    seed = string(row["seed_name"]) if row["seed_name"] is not None else None
    return DeliveryPlan(checks(row["checks"]), pages, boolean(row["shuffle_royals"]), tuple(remote), session, policy, boolean(row["skip_opening"]), boolean(row["skip_dialogue"]), seed)


def encode_plan(plan: DeliveryPlan) -> Json:
    # Normalizing dataclasses/tuples through JSON gives the exact public shape.
    value: Json = json.loads(json.dumps(asdict(plan)))
    decode_plan(value)
    return value


def load_plan_files(path: Path, album_pages: AlbumPages | None = None, shuffle_royals: bool = False, remote_path: Path | None = None, session_path: Path | None = None) -> DeliveryPlan:
    def read(source: Path) -> Json:
        from .seed_patch import unique_object
        if source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Native plan file exceeds the supported size")
        value: Json = json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        return value
    payload: dict[str, Json] = {"checks": read(path), "album_pages": album_pages.value if album_pages else None,
                              "shuffle_royals": shuffle_royals, "remote_rewards": read(remote_path) if remote_path else [],
                              "remote_session": read(session_path) if session_path else None, "sticker_policy": None, "skip_opening": True, "skip_dialogue": True, "seed_name": None}
    return decode_plan(payload)

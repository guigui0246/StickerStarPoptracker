"""Share native check/reward plans without ROM bytes, scripts or game assets."""

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path

from ...data.catalog import Json, obj, string
from ...settings import AlbumPages, GenericStickers, Settings
from .native_delivery import DeliveryPlan, NativeRewardKind
from .plan_io import decode_plan, encode_plan
from .project import RomProject
from .reward_patch import build_reward_mod
from .seed_patch import TITLE_ID, canonical, digest, keys, sha256, unique_object
from .stickers import sticker_policy

MAX_NATIVE_RECIPE_BYTES = 2 * 1024 * 1024


def source_digest(project: RomProject) -> str:
    with project.source.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class NativeRecipe:
    seed: str
    rom_sha256: str
    plan: DeliveryPlan
    settings: Settings | None = None

    def __post_init__(self) -> None:
        if self.plan.seed_name is None:
            object.__setattr__(self, "plan", replace(self.plan, seed_name=self.seed))
        elif self.plan.seed_name != self.seed:
            raise ValueError("Recipe and native save identity use different seeds")
        if self.settings is not None:
            pages = None if self.settings.album_pages == AlbumPages.VANILLA else self.settings.album_pages
            if self.plan.album_pages != pages:
                raise ValueError("Recipe settings disagree with native album policy")
            if self.plan.vanilla_generic_stickers != (self.settings.generic_stickers == GenericStickers.DISABLED):
                raise ValueError("Recipe settings disagree with native sticker policy")

    def encode(self) -> bytes:
        payload: dict[str, Json] = {
            "format_version": 2,
            "algorithm": "native-rewards-v1",
            "mode": "experimental_native_rewards",
            "title_id": TITLE_ID,
            "seed": self.seed,
            "rom_sha256": self.rom_sha256,
            "plan": encode_plan(self.plan),
            "save_seed_fingerprint": self.plan.fingerprint.hex(),
        }
        if self.settings is not None:
            payload["settings"] = dict(self.settings.to_json())
        payload["recipe_sha256"] = digest(canonical(payload))
        return canonical(payload) + b"\n"


def decode_native_recipe(data: bytes) -> NativeRecipe:
    if len(data) > MAX_NATIVE_RECIPE_BYTES:
        raise ValueError("Native stickerpatch exceeds the supported size")
    try:
        payload = obj(json.loads(data, object_pairs_hook=unique_object))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Invalid native stickerpatch JSON") from error
    keys(
        payload,
        {
            "format_version",
            "algorithm",
            "mode",
            "title_id",
            "seed",
            "rom_sha256",
            "plan",
            "save_seed_fingerprint",
            "recipe_sha256",
        } | ({"settings"} if "settings" in payload else set()),
    )
    checksum = sha256(payload.pop("recipe_sha256"))
    if checksum != digest(canonical(payload)):
        raise ValueError("Native stickerpatch checksum mismatch")
    if (
        type(payload["format_version"]) is not int
        or payload["format_version"] != 2
        or payload["algorithm"] != "native-rewards-v1"
        or payload["mode"] != "experimental_native_rewards"
        or payload["title_id"] != TITLE_ID
    ):
        raise ValueError("Unsupported native stickerpatch version or target")
    seed = string(payload["seed"])
    if not seed or len(seed) > 1024:
        raise ValueError("Native recipes require a bounded seed identity")
    plan = decode_plan(payload["plan"])
    if plan.seed_name != seed:
        raise ValueError("Native plan is not bound to this recipe seed")
    if payload["save_seed_fingerprint"] != plan.fingerprint.hex():
        raise ValueError("Native plan does not match its save identity")
    if plan.remote_session and plan.remote_session.seed != seed:
        raise ValueError("Recipe and network session use different seeds")
    settings = Settings.from_json(obj(payload["settings"])) if "settings" in payload else None
    return NativeRecipe(seed, sha256(payload["rom_sha256"]), plan, settings)


def create_native_recipe(project: RomProject, seed: str, plan: DeliveryPlan, settings: Settings | None = None) -> NativeRecipe:
    from .mailbox import fit_mailbox

    rewards = plan.rewards
    if any(reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY} for reward in rewards):
        policy = replace(sticker_policy(project.read_file("Data/kdm_item_data.bin")),
                         randomize_generic=not plan.vanilla_generic_stickers)
        if plan.sticker_policy and plan.sticker_policy != policy:
            raise ValueError("Sticker policy does not match this ROM")
        plan = replace(plan, sticker_policy=policy)
    return decode_native_recipe(NativeRecipe(seed, source_digest(project), fit_mailbox(plan), settings).encode())


def apply_native_recipe(project: RomProject, recipe: NativeRecipe, output: Path, compiler: Path) -> Path:
    recipe = decode_native_recipe(recipe.encode())
    if output.exists() or output.is_symlink():
        raise FileExistsError("Existing mods are preserved; choose a new output folder")
    if source_digest(project) != recipe.rom_sha256:
        raise ValueError("ROM does not match this native stickerpatch")
    return build_reward_mod(project, recipe.plan, compiler, output)

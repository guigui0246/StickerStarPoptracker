"""Build actual KSM overrides for persistent goal-block reward placements."""

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import re
import tempfile

from .kdm import KdmDocument
from .native_delivery import (
    BannerReward,
    DeliveryPlan,
    EnemyReward,
    FlagReward,
    GoalBlockReward,
    NativeRewardKind,
    PickupReward,
    ContainerReward,
    PeelReward,
    ScriptReward,
)
from .pickups import item_pickups, record, text
from .project import RomProject, publish_directory
from .script_build import ScriptSource, add_declarations, compile_checked, decompile, prepend_body, replace_body
from .scene_policy import skip_scene
from .switches import SaveSwitch, global_flags, register_flags, register_saved_bytes
from .royal_patch import (
    FINAL_BOSS,
    INTERMISSIONS,
    ROYAL_GATE_SCRIPT,
    disable_book_restoration,
    suppress_royal_grant,
    shuffled_royal_gate,
)
from .tutorial_skip import compile_script
from .compression import decompress_code
from .stickers import sticker_policy, patch_shops, patch_sticker_initializers
from .presentation import (
    BOSS_PRESENTATION_SCRIPT, MESSAGE_SCRIPT, OPENING_SCRIPT, skip_boss_intros, skip_dialogue, skip_opening,
    skip_royal_intermission,
)
from .enemies import PLAYER_SCRIPT, WIN_SCRIPT, death_hook, enemy_types, reset_hook, victory_hook
from .abilities import ability_patch
from .sticker_guard import generic_save_indices, sticker_guard_patch
from .access import WORLD_MAP_SCRIPT, configure_world_map, gate_stage_entry
from .events import SHOP_SCRIPTS, stages
from .doors import DOOR_IMPORT_SCRIPT, PAPERIZATION_SCRIPT, DoorPlace, door_places, gate_door_fit, validate_door_access
from .startup import STARTUP_FLAGS, STARTUP_SCRIPT, post_tutorial_start, route_start_to_world_map
from .bosses import BOSS_GATES, gate_boss
from .shared_runtime import RUNTIME_SCRIPT, VARIABLE_POOL_LIMIT, runtime_functions, shared_imports
from .runtime_pool import expand_variable_pool
from .scraps import scripted_scraps
from .containers import TREASURE_SCRIPT, container_sources, hook_treasure_acquisition
from .peels import PeelSource, resolve_peels, suppress_peel_grants, hook_peel_callback, gate_peel_selection
from .things import (
    SCRIPTED_THING_SCRIPTS,
    scripted_things,
    thing_effect_scripts,
    hook_thing_initialization,
    hook_thing_effects,
)


def apply_event_hooks(source: str, hooks: list[tuple[int, ScriptReward]], plan: DeliveryPlan) -> str:
    for index, check in hooks:
        checked, _ = plan.receipt(index)
        body = "\ttemp tempVar90 = rando_seed_valid*();\n\tif ( tempVar90 == false ) {\n\t\treturn*;\n\t}\n"
        if check.reward.kind == NativeRewardKind.VICTORY:
            body += (
                "\ttempVar90 = battle_get_result*();\n\tif ( tempVar90 == r"
                "esult_win ) {\n\t\t"
                f"{checked}"
                " *= true;\n\t\trando_deliver*();\n\t}\n"
            )
        else:
            body += f"\t{checked} *= true;\n\trando_deliver*();\n"
        source = prepend_body(source, check.function, body)
    return source


def build_reward_mod(project: RomProject, plan: DeliveryPlan, compiler: Path, output: Path) -> Path:
    compiler = compiler.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Use a new output folder to preserve existing mods")
    switch_source = project.read_file("Data/kdm_switch.bin")
    known_flags = {flag.name for flag in global_flags(KdmDocument(switch_source))}
    item_source = project.read_file("Data/kdm_item_data.bin")
    item_table = KdmDocument(item_source)
    rewards = plan.rewards
    observed_doors: tuple[DoorPlace, ...] = ()
    if plan.door_access_codes:
        world_stages = stages(KdmDocument(project.read_file("Data/kdm_worldmap_data.bin")))
        observed_doors = door_places(project.read_file("Data/kdm_pepalyze.bin"), world_stages)
        validate_door_access(plan, observed_doors)
        if any(isinstance(check, ScriptReward) and check.script_file == PAPERIZATION_SCRIPT for check in plan.checks):
            raise ValueError("Paperization admission script cannot also be a check hook")
    if plan.stage_access_codes:
        known_stages = {stage.code for stage in stages(KdmDocument(project.read_file("Data/kdm_worldmap_data.bin")))}
        if set(plan.stage_access_codes) - known_stages:
            raise ValueError("Admission reward references an unknown native world-map stage")
        if any(isinstance(check, ScriptReward) and check.script_file == WORLD_MAP_SCRIPT for check in plan.checks):
            raise ValueError("World-map admission script cannot also be a check hook")
    if plan.ability_mode and any(reward.kind == NativeRewardKind.ITEM and reward.value == "IC_HAMMER" for reward in rewards):
        raise ValueError("Hammer rewards must use the shuffled ability capability")
    if plan.ability_mode and set(STARTUP_FLAGS) - known_flags:
        raise ValueError("Required original tutorial completion flags are missing")
    if plan.ability_mode and any(
        isinstance(check, ScriptReward) and check.script_file == STARTUP_SCRIPT for check in plan.checks
    ):
        raise ValueError("Startup script cannot also be a check hook")
    if any(reward.kind in {NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY} for reward in rewards):
        observed_policy = replace(sticker_policy(item_source), randomize_generic=not plan.vanilla_generic_stickers)
        if plan.sticker_policy is not None and plan.sticker_policy != observed_policy:
            raise ValueError("Sticker policy does not match this ROM")
        plan = replace(plan, sticker_policy=observed_policy)
        for reward in rewards:
            if reward.kind == NativeRewardKind.ITEM and reward.value in observed_policy.generic:
                raise ValueError("Generic rewards must explicitly be sticker_unlock or sticker_copy")
    known_items = {
        text(record(row, 19)[0]) for array in item_table.arrays.values() if array.type_id == 30 for row in array.values
    }
    for check in plan.checks:
        if isinstance(check, ScriptReward) and check.category == "shop":
            binding = SHOP_SCRIPTS.get(check.script_file)
            if binding is None or binding[1] != check.function:
                raise ValueError("Shop checks must use an observed first-conversation callback, not shop initialization")
        if isinstance(check, FlagReward) and check.source_flag not in known_flags:
            raise ValueError(f"Unknown event flag: {check.source_flag}")
        if isinstance(check, GoalBlockReward) and check.source_flag.lower() not in known_flags:
            raise ValueError(f"Unknown source route flag: {check.source_flag}")
        if (
            check.reward.kind in {NativeRewardKind.ITEM, NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}
            and check.reward.value not in known_items
        ):
            raise ValueError(f"Unknown reward item: {check.reward.value}")
        if check.reward.kind == NativeRewardKind.MINI_STAR and str(check.reward.value).lower() not in known_flags:
            raise ValueError(f"Unknown received route flag: {check.reward.value}")
    for entry in plan.remote_rewards:
        if (
            entry.reward.kind in {NativeRewardKind.ITEM, NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}
            and entry.reward.value not in known_items
        ):
            raise ValueError("Remote selector references an unknown native item")
        if entry.reward.kind == NativeRewardKind.MINI_STAR and str(entry.reward.value).lower() not in known_flags:
            raise ValueError("Remote selector references an unknown route")
    for reward in plan.starting_rewards:
        if (
            reward.kind in {NativeRewardKind.ITEM, NativeRewardKind.STICKER_UNLOCK, NativeRewardKind.STICKER_COPY}
            and reward.value not in known_items
        ):
            raise ValueError("Starting inventory references an unknown native item")
        if reward.kind == NativeRewardKind.MINI_STAR and str(reward.value).lower() not in known_flags:
            raise ValueError("Starting inventory references an unknown route")
    pickup_checks = tuple(check for check in plan.checks if isinstance(check, PickupReward))
    container_checks = tuple(check for check in plan.checks if isinstance(check, ContainerReward))
    observed_containers = (
        container_sources(KdmDocument(project.read_file("Data/kdm_dispos_data.bin"))) if container_checks else ()
    )
    native_containers = {(entry.map_name, entry.object_name): entry for entry in observed_containers}
    for check in container_checks:
        observed_container = native_containers.get((check.map_name, check.object_name))
        if observed_container is None or (observed_container.source_item, observed_container.container_type) != (
            check.source_item,
            check.container_type,
        ):
            raise ValueError("Container check does not match one deterministic native reward")
        if any(
            isinstance(other, PickupReward) and other.map_name == check.map_name and other.source_item == check.source_item
            for other in plan.checks
        ):
            raise ValueError("Container reward duplicates a field stand-in in the same map")
    peel_table = KdmDocument(project.read_file("Data/kdm_pepalyze.bin"))
    peel_checks = resolve_peels(peel_table, plan)
    peel_scripts: dict[str, list[tuple[int, PeelReward, PeelSource]]] = {}
    for peel_index, check, observed_source in peel_checks:
        if any(hook.source_item not in known_items for hook in check.hooks):
            raise ValueError("Peel source references an unknown native scrap")
        candidates = [
            entry.name
            for entry in project.inspection.romfs
            if entry.name.startswith("Script/Map/") and entry.name.endswith(f"/{check.map_name}.bin")
        ]
        if len(candidates) != 1:
            raise ValueError("Peel source does not identify one original map script")
        peel_scripts.setdefault(candidates[0], []).append((peel_index, check, observed_source))
        if any(
            isinstance(other, ScriptReward)
            and other.script_file == candidates[0]
            and other.function == observed_source.callback
            for other in plan.checks
        ):
            raise ValueError("Peel callback cannot also be an independent script check")
    enemy_checks = tuple((index, check) for index, check in enumerate(plan.checks) if isinstance(check, EnemyReward))
    if enemy_checks:
        observed_enemies = {enemy.unit_id: enemy for enemy in enemy_types(project.read_file("Data/kdm_battle.bin"))}
        for _, check in enemy_checks:
            for hook in check.hooks:
                enemy = observed_enemies.get(hook.unit_id)
                if (
                    enemy is None
                    or not enemy.death_function
                    or (enemy.script_file, enemy.death_function) != (hook.script_file, hook.function)
                ):
                    raise ValueError("Enemy hook does not match the native unit definition")
                if check.type_id is not None and enemy.name_label != check.type_id:
                    raise ValueError("Enemy variant does not belong to this native type label")
        overlap = {PLAYER_SCRIPT, WIN_SCRIPT, *(hook.script_file for _, check in enemy_checks for hook in check.hooks)}
        if any(isinstance(check, ScriptReward) and check.script_file in overlap for check in plan.checks):
            raise ValueError("Enemy hooks must not overlap general script checks")
    if pickup_checks:
        observed = item_pickups(KdmDocument(project.read_file("Data/kdm_dispos_data.bin")))
        for check in pickup_checks:
            matches = [item for item in observed if (item.map_name, item.object_name) == (check.map_name, check.object_name)]
            if not matches and check.source_item.startswith("REAL_"):
                filename = SCRIPTED_THING_SCRIPTS.get(check.map_name)
                if filename is None:
                    raise ValueError(f"Unknown scripted Thing source: {check.id}")
                with tempfile.TemporaryDirectory(prefix=".thing-source-") as directory:
                    original = decompile(project, filename, Path(directory), compiler)
                    scripted_thing = scripted_things(check.map_name, original.source.read_text(encoding="utf-8"))
                if not any(
                    (entry.object_name, entry.source_item) == (check.object_name, check.source_item)
                    for entry in scripted_thing
                ):
                    raise ValueError(f"Scripted Thing does not match its native acquisition: {check.id}")
                continue
            if not matches and check.source_item.startswith("PK_FIELD_"):
                candidates = [
                    entry.name
                    for entry in project.inspection.romfs
                    if entry.name.startswith("Script/Map/") and entry.name.endswith(f"/{check.map_name}.bin")
                ]
                if len(candidates) != 1:
                    raise ValueError("Scripted scrap has no unique original map script")
                with tempfile.TemporaryDirectory(prefix=".scrap-source-") as directory:
                    original = decompile(project, candidates[0], Path(directory), compiler)
                    scripted = scripted_scraps(check.map_name, original.source.read_text(encoding="utf-8"))
                if not any((item.object_name, item.field_item) == (check.object_name, check.source_item) for item in scripted):
                    raise ValueError(f"Scripted scrap does not match a named native static entry: {check.id}")
                continue
            if len(matches) != 1 or matches[0].item_name != check.source_item:
                raise ValueError(f"Pickup does not match one observed disposition: {check.id}")
        plan.piece_pickup_function()
    switch_patch, allocated = register_flags(switch_source, plan.flags)
    saved_allocated: tuple[SaveSwitch, ...] = ()
    if plan.saved_bytes:
        switch_patch, saved_allocated = register_saved_bytes(switch_patch, plan.saved_bytes)
    if plan.remote_rewards and allocated[0].index != 1446:
        raise ValueError("This RPC memory profile requires the inspected flag registry revision")
    rpc_profile: dict[str, object] | None = None
    code_patch = None
    flag_indices = {flag.name: flag.index for flag in (*global_flags(KdmDocument(switch_source)), *allocated)}
    if plan.checks:
        code = decompress_code(project.read_exefs(".code"))
        if (
            len(code) != 0x34E000
            or int.from_bytes(code[0x920A0:0x920A4], "little") != 0x43C190
            or int.from_bytes(code[0x182D74:0x182D78], "little") != 0xE5912144
        ):
            raise ValueError("Executable does not match the inspected GF memory layout")
        rpc_profile = {
            "pointer_address": 0x43C190,
            "global_flags_offset": 0x144,
            "flag_count": 3072,
            "signature_address": 0x282C98,
            "signature_size": 0x160,
            "signature_sha256": hashlib.sha256(code[0x182C98:0x182DF8]).hexdigest(),
        }
        if plan.saved_bytes:
            if int.from_bytes(code[0x194068:0x19406C], "little") != 0xA5C04004:
                raise ValueError("Executable does not match the native GS byte setter")
            rpc_profile["saved_bytes_offset"] = 4
            rpc_profile["saved_bytes_count"] = 256
            rpc_profile["saved_byte_signature"] = {
                "address": 0x29404C,
                "size": 0x24,
                "sha256": hashlib.sha256(code[0x19404C:0x194070]).hexdigest(),
            }
        if plan.ability_mode or plan.sticker_policy:
            if project.codeset_layout() != ((0x100000, 0x2D7, 0x2D6BB8), (0x3D7000, 0x41, 0x40D2C), (0x418000, 0x36, 0x35CF4)):
                raise ValueError("Executable segment layout does not match the bounded native hooks")
        if plan.ability_mode:
            code_patch = ability_patch(code, flag_indices, plan.fingerprint)
        if plan.sticker_policy and plan.sticker_policy.randomize_generic:
            code_patch = sticker_guard_patch(
                code,
                flag_indices,
                plan.fingerprint,
                plan.sticker_policy,
                generic_save_indices(item_source, plan.sticker_policy),
                code_patch,
            )
        code_patch = expand_variable_pool(code, code_patch)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".native-rewards-", dir=output.parent) as temporary:
        staging = Path(temporary) / "mod"
        work = Path(temporary) / "build"
        map_scripts = {
            name: decompile(project, name, work, compiler)
            for name in ("Script/ksm_mobj.bin", "Script/ksm_map.bin", "Script/ksm_evtcond.bin", "Script/Map/MAC/mac_1_00.bin")
        }
        source_effect_scripts = thing_effect_scripts(plan)
        for filename in source_effect_scripts:
            map_scripts[filename] = decompile(project, filename, work, compiler)
        if plan.ability_mode or plan.stage_access_codes or plan.open_ground_routes or plan.starting_stage:
            map_scripts[WORLD_MAP_SCRIPT] = decompile(project, WORLD_MAP_SCRIPT, work, compiler)
        if plan.ability_mode:
            map_scripts[STARTUP_SCRIPT] = decompile(project, STARTUP_SCRIPT, work, compiler)
        if plan.shuffle_royals:
            map_scripts[ROYAL_GATE_SCRIPT] = decompile(project, ROYAL_GATE_SCRIPT, work, compiler)
        boss_scripts = {BOSS_GATES[code].script_file: BOSS_GATES[code] for code in plan.boss_access_codes}
        for filename in boss_scripts:
            map_scripts[filename] = decompile(project, filename, work, compiler)
        for filename in peel_scripts:
            if filename not in map_scripts:
                map_scripts[filename] = decompile(project, filename, work, compiler)
        sources: dict[str, str] = {}
        for check in plan.checks:
            if not isinstance(check, GoalBlockReward):
                continue
            candidates = [
                entry.name
                for entry in project.inspection.romfs
                if entry.name.startswith("Script/Map/") and entry.name.endswith(f"/{check.map_name}.bin")
            ]
            if len(candidates) != 1:
                raise ValueError(f"Cannot identify source map script: {check.map_name}")
            filename = candidates[0]
            if filename not in sources:
                source_script = decompile(project, filename, work, compiler)
                sources[filename] = source_script.source.read_text(encoding="utf-8")
            pattern = r'mobj_goal_block_exit\*?\(self, "' + re.escape(check.source_flag) + r'"\);'
            if len(re.findall(pattern, sources[filename])) != 1:
                raise ValueError(f"Check does not match one observed goal-block call: {check.id}")
        # Import declarations are harvested from the user's original scripts,
        # rather than assuming native function IDs or distributing game headers.
        coin_script = decompile(project, "Script/Map/MAC/mac_1_04.bin", work, compiler)
        item_script = decompile(project, "Script/ksm_item.bin", work, compiler)
        map_scripts["Script/ksm_item.bin"] = item_script
        field_script = decompile(project, "Script/ksm_field.bin", work, compiler)
        album_scripts = (
            (decompile(project, "Script/Map/W3_SAR/w3_sar_00.bin", work, compiler),) if plan.album_pages is not None else ()
        )
        banner_checks = tuple(check for check in plan.checks if isinstance(check, BannerReward))
        banner_scripts = (decompile(project, "Script/Map/MAC/mac_1_F.bin", work, compiler),) if banner_checks else ()
        final_scripts = (
            (decompile(project, FINAL_BOSS, work, compiler),)
            if any(isinstance(check, ScriptReward) and check.script_file == FINAL_BOSS for check in plan.checks)
            else ()
        )
        battle_scripts = (
            tuple(
                decompile(project, filename, work, compiler)
                for filename in (
                    "Script/Battle/Player/battle_mario_balloon.bin",
                    "Script/Battle/ksm_battle_event.bin",
                    "Script/Battle/ksm_battle_ui.bin",
                )
            )
            if enemy_checks
            else ()
        )
        ability_scripts = (
            tuple(
                decompile(project, filename, work, compiler)
                for filename in (
                    "Script/Map/MAC/mac_1_31.bin",
                    "Script/Map/W3_SAR/w3_sar_00.bin",
                    "Script/Map/W3_BEA/w3_bea_01.bin",
                )
            )
            if plan.ability_mode
            else ()
        )
        boss_import_scripts = (
            (decompile(project, BOSS_GATES["w4"].script_file, work, compiler),) if plan.boss_pending_flags else ()
        )
        peel_import_scripts = (decompile(project, DOOR_IMPORT_SCRIPT, work, compiler),) if peel_checks else ()
        imports: dict[str, str] = {}
        for script in (
            *map_scripts.values(),
            coin_script,
            item_script,
            field_script,
            *album_scripts,
            *banner_scripts,
            *final_scripts,
            *battle_scripts,
            *ability_scripts,
            *boss_import_scripts,
            *peel_import_scripts,
        ):
            header = script.header.read_text(encoding="utf-8")
            for declaration in header.splitlines():
                match = re.match(r"#import (?:function|int) ([a-zA-Z0-9_]+) from .*;", declaration)
                if match:
                    imports.setdefault(match[1], declaration)
        required = {
            "item_try_addpouch",
            "pouch_add_coin",
            "pouch_set_royal_seal",
            "mobj_set_gf",
            "wm_set_gf",
            "pouch_get_map_name",
        }
        required.update(
            f"pouch_royal_w{check.reward.value}" for check in plan.checks if check.reward.kind == NativeRewardKind.ROYAL
        )
        required.update(
            f"pouch_royal_w{entry.reward.value}"
            for entry in plan.remote_rewards
            if entry.reward.kind == NativeRewardKind.ROYAL
        )
        required.update(
            f"pouch_royal_w{reward.value}" for reward in plan.starting_rewards if reward.kind == NativeRewardKind.ROYAL
        )
        if banner_checks:
            required.update(("pouch_honor_get_value", "pouch_honor_get_max"))
            required.update(f"honor_id_{check.honor}" for check in banner_checks)
        if any(check.reward.kind == NativeRewardKind.VICTORY for check in plan.checks):
            required.update(("battle_get_result", "result_win"))
        if plan.sticker_policy:
            required.update(
                (
                    "item_set_flg",
                    "item_flg_add_pouch",
                    "item_set_itemget_event",
                    "item_get_item_id",
                    "character_hide",
                    "item_delete",
                    "pouch_already_get_real_item_debug",
                )
            )
        if enemy_checks:
            required.update(("battle_unit_get_hp", "battle_unit_get_unit_data_id", "battle_is_museum"))
        if plan.ability_mode:
            required.update(
                (
                    "pouch_attach_accessory",
                    "pouch_detach_accessory",
                    "pouch_hammer",
                    "pouch_lucie",
                    "player_set_ignore_key",
                    "player_hammer_button",
                    "player_pepalyze_button",
                )
            )
            required.update(("map_exit_event", "ui_enable_open_status_all"))
        if peel_import_scripts:
            required.update(("pepalyze_get_now_play_unlock_num", "pepalyze_get_access_number"))
        if plan.boss_pending_flags:
            required.update(("case_cancel", "case_uncancel"))
        if required - imports.keys():
            raise ValueError(f"Missing observed native imports: {sorted(required - imports.keys())}")
        native_imports = {name: imports[name] for name in sorted(required)}
        emitted: dict[str, str] = {}
        required_flags: tuple[str, ...]
        if plan.door_access_codes or peel_checks:
            donor = decompile(project, DOOR_IMPORT_SCRIPT, work, compiler)
            door_imports = {}
            for declaration in donor.header.read_text(encoding="utf-8").splitlines():
                match = re.match(
                    "#import function (pepalyze_get_now_play_unlock_num|pepalyze_get_a"
                    "ccess_number|pepalyze_is_now_play_unlock) from .*;",
                    declaration,
                )
                if match:
                    door_imports[match[1]] = declaration
            if len(door_imports) != 3:
                raise ValueError("Missing original Paperization target identity imports")
            door_imports["pouch_get_map_name"] = native_imports["pouch_get_map_name"]
            script = decompile(project, PAPERIZATION_SCRIPT, work, compiler)
            selection_source = script.source.read_text(encoding="utf-8")
            if plan.door_access_codes:
                selection_source = gate_door_fit(selection_source, plan, observed_doors, shared_seed=True)
            if peel_checks:
                selection_source = gate_peel_selection(selection_source, plan, peel_table)
            script.source.write_text(selection_source, encoding="utf-8")
            required_flags = tuple(
                f"gf_rando_door_{code.lower()}"
                for code in plan.door_access_codes
                if any(code in (place.stage_code, place.lock_id) for place in observed_doors)
            )
            script.header.write_text(
                add_declarations(script.header.read_text(encoding="utf-8"), required_flags, door_imports | shared_imports()),
                encoding="utf-8",
            )
            data = compile_checked(
                script,
                compiler,
                required_flags,
                required_function="rando_peel_control" if peel_checks else "rando_door_control",
            )
            project.write_override(staging, PAPERIZATION_SCRIPT, data)
            emitted[PAPERIZATION_SCRIPT] = hashlib.sha256(data).hexdigest()
        if container_checks:
            script = decompile(project, TREASURE_SCRIPT, work, compiler)
            script.source.write_text(hook_treasure_acquisition(script.source.read_text(encoding="utf-8")), encoding="utf-8")
            script.header.write_text(
                add_declarations(script.header.read_text(encoding="utf-8"), (), shared_imports()), encoding="utf-8"
            )
            data = compile_checked(script, compiler, (), required_function="rando_container_collect")
            project.write_override(staging, TREASURE_SCRIPT, data)
            emitted[TREASURE_SCRIPT] = hashlib.sha256(data).hexdigest()
        if enemy_checks:
            enemy_scripts: dict[str, dict[str, list[tuple[int, EnemyReward]]]] = {}
            for index, check in enemy_checks:
                for hook in check.hooks:
                    alias = EnemyReward(hook.unit_id, hook.script_file, hook.function, check.reward)
                    enemy_scripts.setdefault(hook.script_file, {}).setdefault(hook.function, []).append((index, alias))
            for filename in (PLAYER_SCRIPT, WIN_SCRIPT, *sorted(enemy_scripts)):
                script = decompile(project, filename, work, compiler)
                source = script.source.read_text(encoding="utf-8")
                required_flags = ()
                if filename == PLAYER_SCRIPT:
                    source = reset_hook(source, plan)
                elif filename == WIN_SCRIPT:
                    source = victory_hook(source, plan)
                    required_flags += tuple(plan.receipt(index)[0] for index, _ in enemy_checks)
                else:
                    for function, death_checks in enemy_scripts[filename].items():
                        source = death_hook(source, function, death_checks, plan)
                script.source.write_text(source, encoding="utf-8")
                script.header.write_text(
                    add_declarations(
                        script.header.read_text(encoding="utf-8"), required_flags, native_imports | shared_imports()
                    ),
                    encoding="utf-8",
                )
                data = compile_checked(script, compiler, required_flags, required_function="rando_seed_valid")
                project.write_override(staging, filename, data)
                emitted[filename] = hashlib.sha256(data).hexdigest()
        presentation_scripts = []
        if plan.skip_opening:
            presentation_scripts.append((OPENING_SCRIPT, skip_opening))
            presentation_scripts.append((BOSS_PRESENTATION_SCRIPT, skip_boss_intros))
        if plan.skip_dialogue:
            presentation_scripts.append((MESSAGE_SCRIPT, skip_dialogue))
        for filename, transform in presentation_scripts:
            if any(isinstance(check, ScriptReward) and check.script_file == filename for check in plan.checks):
                raise ValueError("Presentation script cannot also be a gameplay check hook")
            script = decompile(project, filename, work, compiler)
            script.source.write_text(transform(script.source.read_text(encoding="utf-8")), encoding="utf-8")
            data = compile_checked(script, compiler, (), required_function=None)
            project.write_override(staging, filename, data)
            emitted[filename] = hashlib.sha256(data).hexdigest()
        suppressed_pages: list[str] = []
        if plan.album_pages is not None or plan.shuffle_royals or plan.skip_opening:
            page_sources = INTERMISSIONS + ("Script/Map/HEI/hei_2_01.bin",) if plan.album_pages is not None else INTERMISSIONS
            for filename in page_sources:
                if any(isinstance(check, ScriptReward) and check.script_file == filename for check in plan.checks):
                    raise ValueError("Intermission/page presentation cannot also be a gameplay check hook")
                script = decompile(project, filename, work, compiler)
                source = script.source.read_text(encoding="utf-8")
                if plan.album_pages is not None:
                    source, count = re.subn(r'\bitem_try_addpouch\*?\("SL_PAGE", true\);', "", source)
                    if count != 1:
                        raise ValueError(f"Expected one vanilla page grant in {filename}")
                if plan.shuffle_royals and filename in INTERMISSIONS:
                    source = suppress_royal_grant(filename, source)
                if plan.skip_opening and filename in INTERMISSIONS:
                    source = skip_royal_intermission(source, INTERMISSIONS.index(filename) + 1)
                script.source.write_text(source, encoding="utf-8")
                data = compile_checked(script, compiler, (), required_function=None)
                if plan.album_pages is not None and "SL_PAGE" in script.binary.with_suffix(".re.cksm").read_text(
                    encoding="utf-8"
                ):
                    raise ValueError("Compiled script retained a vanilla page grant")
                project.write_override(staging, filename, data)
                emitted[filename] = hashlib.sha256(data).hexdigest()
                if plan.album_pages is not None:
                    suppressed_pages.append(filename)
        if plan.shuffle_royals:
            script = map_scripts["Script/ksm_evtcond.bin"]
            data = disable_book_restoration(script.binary.read_bytes())
            script.binary.write_bytes(data)
            compile_script(compiler, script.binary)
            canonical = script.source.read_text(encoding="utf-8")
            body = canonical.split("private royalseal_book_reset()", 1)[1].split("\nprivate ", 1)[0]
            if "return;" not in body or "evtcond_pouch_clear" in body or "pouch_set_royal_seal" in body:
                raise ValueError("Royal restoration suppression failed decompilation verification")
            project.write_override(staging, "Script/ksm_evtcond.bin", data)
            emitted["Script/ksm_evtcond.bin"] = hashlib.sha256(data).hexdigest()
        script_checks = tuple((index, check) for index, check in enumerate(plan.checks) if isinstance(check, ScriptReward))
        hooked_scripts: dict[str, list[tuple[int, ScriptReward]]] = {}
        for index, check in script_checks:
            hooked_scripts.setdefault(check.script_file, []).append((index, check))
        for filename, hooks in hooked_scripts.items():
            if filename in map_scripts:
                continue  # compose with the shared delivery transformation below
            if filename in suppressed_pages:
                raise ValueError("Script hook overlaps another transformation; compose it explicitly")
            script = decompile(project, filename, work, compiler)
            source = script.source.read_text(encoding="utf-8")
            if plan.shuffle_royals and filename == FINAL_BOSS:
                source = suppress_royal_grant(filename, source)
            source = apply_event_hooks(source, hooks, plan)
            script.source.write_text(source, encoding="utf-8")
            script.header.write_text(
                add_declarations(
                    script.header.read_text(encoding="utf-8"), plan.references, native_imports | shared_imports()
                ),
                encoding="utf-8",
            )
            required_flags = tuple(plan.receipt(index)[0] for index, _ in hooks)
            data = compile_checked(script, compiler, required_flags)
            project.write_override(staging, filename, data)
            emitted[filename] = hashlib.sha256(data).hexdigest()
        delivery_scripts: tuple[str, ...] = (
            "Script/ksm_mobj.bin",
            "Script/ksm_map.bin",
            "Script/Map/MAC/mac_1_00.bin",
            RUNTIME_SCRIPT,
        )
        if plan.ability_mode or plan.stage_access_codes or plan.open_ground_routes or plan.starting_stage:
            delivery_scripts += (WORLD_MAP_SCRIPT,)
        if plan.ability_mode:
            delivery_scripts += (STARTUP_SCRIPT,)
        delivery_scripts += tuple(boss_scripts)
        delivery_scripts += source_effect_scripts
        if plan.shuffle_royals:
            delivery_scripts += (ROYAL_GATE_SCRIPT,)
        delivery_scripts = tuple(dict.fromkeys(delivery_scripts + tuple(peel_scripts)))
        for filename in delivery_scripts:
            script = map_scripts[filename]
            source = script.source.read_text(encoding="utf-8")
            if "rando_deliver" in source:
                raise ValueError("Source is already patched for randomized rewards")
            if filename in boss_scripts and plan.shuffle_royals and filename == FINAL_BOSS:
                source = suppress_royal_grant(filename, source)
            source = apply_event_hooks(source, hooked_scripts.get(filename, []), plan)
            for index, check, observed_source in peel_scripts.get(filename, []):
                source = hook_peel_callback(source, index, check, observed_source)
            if filename in boss_scripts:
                source = gate_boss(source, boss_scripts[filename], require_royals=plan.shuffle_royals)
                source = prepend_body(source, "init", "\trando_deliver*();\n\tthread rando_delivery_poll*();\n")
                source += "\n" + plan.polling_function()
            elif filename == WORLD_MAP_SCRIPT:
                source = configure_world_map(source, plan, known_flags)
                if plan.stage_access_codes:
                    source = gate_stage_entry(source, plan)
                source = prepend_body(source, "e_worldmap", "\trando_deliver*();\n\tchildthread rando_delivery_poll*();\n")
                source += "\n" + plan.polling_function()
            elif filename == STARTUP_SCRIPT:
                source = post_tutorial_start(source)
            elif filename == ROYAL_GATE_SCRIPT:
                source = shuffled_royal_gate(source)
                source = prepend_body(source, "init", "\trando_deliver*();\n")
            elif filename.endswith("ksm_mobj.bin"):
                source = replace_body(source, "mobj_goal_block_exit", plan.goal_block_body())
            elif filename.endswith("ksm_item.bin"):
                if pickup_checks or container_checks:
                    if any(check.source_item.startswith("REAL_") for check in pickup_checks):
                        source = hook_thing_initialization(source)
                    source = prepend_body(
                        source,
                        "item_get_evt_real",
                        "\ttemp tempVar90 = rando_pickup*(tempVar0);\n\tif ( tempVar90 == -1 "
                        ") {\n\t\treturn*;\n\t}\n\tif ( tempVar90 ) {\n\t\tcharacter_hide*(tempVar0)"
                        ";\n\t\titem_delete*(tempVar0, 0);\n\t\treturn*;\n\t}\n",
                    )
                    source = prepend_body(
                        source,
                        "item_get_real_name",
                        "\ttemp tempVar90 = rando_pickup*(tempVar0);\n\tif ( tempVar90 == -1 "
                        ") {\n\t\treturn*;\n\t}\n\tif ( tempVar90 ) {\n\t\tcharacter_hide*(tempVar0)"
                        ";\n\t\titem_delete*(tempVar0, 0);\n\t\treturn*;\n\t}\n",
                    )
                    source = prepend_body(
                        source,
                        "map_piece_get",
                        "\ttemp tempVar90 = character_get_name*();\n\ttempVar90 = rando_picku"
                        "p*(tempVar90);\n\tif ( tempVar90 == -1 ) {\n\t\treturn*;\n\t}\n\tif ( temp"
                        "Var90 ) {\n\t\titem_delete_effect*(self, true);\n\t\tcharacter_hide*(se"
                        "lf);\n\t\treturn*;\n\t}\n",
                    )
                    source += "\n" + plan.pickup_function()
                    if any(check.source_item.startswith("PK_FIELD_") for check in pickup_checks) or any(
                        check.source_item.startswith("PK_FIELD_") for check in container_checks
                    ):
                        source = prepend_body(
                            source,
                            "item_get_evt_piece",
                            "\ttemp tempVar90 = rando_piece_pickup*(tempVar0);\n\tif ( tempVar90 "
                            "!= false ) {\n\t\treturn*;\n\t}\n",
                        )
                        source += "\n" + plan.piece_pickup_function()
                if plan.sticker_policy:
                    source += "\n" + plan.sticker_policy.pickup_functions()
            elif filename.endswith("ksm_map.bin"):
                # The layout helper handles default, detail and BGM-synced maps.
                # The native item spawning and initialization calls are preserved.
                marker = "\tnpc_wait_initialized_all*();"
                if source.count(marker) < 1:
                    raise ValueError("Expected layout initialization barrier")
                source = source.replace(marker, marker + "\n\trando_deliver*();\n\tthread rando_delivery_poll*();")
                source += "\n" + plan.polling_function()
            elif filename == "Script/Map/MAC/mac_1_00.bin":
                marker = '\titem_entry_dispos*("mac_1_00");'
                if source.count(marker) != 1:
                    raise ValueError("Expected one Decalburg initialization barrier")
                source = source.replace(marker, marker + "\n\trando_deliver*();\n\tthread rando_delivery_poll*();")
                source += "\n" + plan.polling_function()
            source = hook_thing_effects(source, filename, plan)
            if filename == RUNTIME_SCRIPT:
                source += runtime_functions(plan)
            script.source.write_text(source, encoding="utf-8")
            script.header.write_text(
                add_declarations(
                    script.header.read_text(encoding="utf-8"),
                    plan.references,
                    native_imports if filename == RUNTIME_SCRIPT else native_imports | shared_imports(),
                ),
                encoding="utf-8",
            )
            if filename == RUNTIME_SCRIPT:
                with script.header.open("a", encoding="utf-8") as header:
                    header.write("".join(f"static bool {flag} = false;\n" for flag in plan.enemy_pending_flags))
                    if peel_checks:
                        header.write("static int rando_peel_reserve = 0;\n")
            if filename == STARTUP_SCRIPT:
                script.header.write_text(
                    add_declarations(script.header.read_text(encoding="utf-8"), STARTUP_FLAGS, {}), encoding="utf-8"
                )
            required_flags = (
                (plan.required_references + (plan.sticker_policy.flags if plan.sticker_policy else ()))
                if filename == RUNTIME_SCRIPT
                else tuple(flag for flag in plan.references if re.search(r"\b" + re.escape(flag) + r"\b", source))
            )
            if filename in boss_scripts and boss_scripts[filename].case_name:
                required_flags += (f"gf_rando_boss_pending_{boss_scripts[filename].code}",)
            required_function = (
                "rando_deliver"
                if "rando_deliver" in source
                else (
                    "rando_thing_source_collected"
                    if "rando_thing_source_collected" in source
                    else ("real_obj_init" if filename in source_effect_scripts else "rando_peel_collect")
                )
            )
            data = compile_checked(script, compiler, required_flags, required_function=required_function)
            project.write_override(staging, filename, data)
            emitted[filename] = hashlib.sha256(data).hexdigest()
        project.write_override(staging, "Data/kdm_switch.bin", switch_patch)
        if peel_checks:
            project.write_override(staging, "Data/kdm_pepalyze.bin", suppress_peel_grants(peel_table, plan))
        if plan.ability_mode:
            project.write_override(
                staging, "Data/kdm_link_data.bin", route_start_to_world_map(project.read_file("Data/kdm_link_data.bin"))
            )
        if plan.sticker_policy:
            project.write_override(
                staging, "Data/kdm_item_data.bin", patch_sticker_initializers(item_source, plan.sticker_policy)
            )
            project.write_override(
                staging, "Data/kdm_shop.bin", patch_shops(project.read_file("Data/kdm_shop.bin"), plan.sticker_policy)
            )
        if code_patch:
            (staging / "exefs").mkdir()
            (staging / "exefs" / "code.ips").write_bytes(code_patch.ips())
            (staging / "exefs" / "code.S").write_text(code_patch.assembly, encoding="utf-8")
            if plan.ability_mode:
                (staging / "exefs" / "abilities.S").write_text(code_patch.assembly, encoding="utf-8")
        # Compose author-provided presentation bindings after all gameplay
        # hooks. Decode the staged result when present, never overwrite it with
        # an unpatched original. skip_scene refuses entries containing hooks.
        for scene in plan.scene_skips:
            binary = work / "scene-policy" / scene.script_file
            binary.parent.mkdir(parents=True, exist_ok=True)
            staged = staging / "romfs" / scene.script_file
            original = staged.read_bytes() if staged.exists() else project.read_file(scene.script_file)
            binary.write_bytes(original)
            compile_script(compiler, binary)
            script = ScriptSource(binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"),
                                  hashlib.sha256(original).hexdigest())
            script.source.write_text(skip_scene(script.source.read_text(encoding="utf-8"), scene), encoding="utf-8")
            compiled = compile_checked(script, compiler, (), required_function=None)
            project.write_override(staging, scene.script_file, compiled)
            emitted[scene.script_file] = hashlib.sha256(compiled).hexdigest()
        report = {
            "format_version": 1,
            "mode": "native_goal_block_rewards",
            "shared_runtime_script": RUNTIME_SCRIPT,
            "script_variable_pool_limit": VARIABLE_POOL_LIMIT,
            "complete_randomizer": False,
            "emulator_verified": False,
            "title_id": project.inspection.title_id,
            "save_seed_fingerprint": plan.fingerprint.hex(),
            "seed_name": plan.seed_name,
            "catalog_hash": plan.catalog_hash or (plan.remote_session.catalog_hash if plan.remote_session else None),
            "starting_rewards": [asdict(reward) for reward in plan.starting_rewards],
            "starting_flags": [flag_indices[flag] for flag in plan.starting_flags],
            "starting_item_ids": list(plan.starting_item_ids),
            "album_pages": plan.album_pages,
            "stage_access_gates": list(plan.stage_access_codes),
            "map_policy": {"open_ground_routes": plan.open_ground_routes, "starting_stage": plan.starting_stage,
                           "gameplay_verified": False},
            "door_access_gates": list(plan.door_access_codes),
            "boss_access_gates": list(plan.boss_access_codes),
            "door_places": [asdict(place) for place in observed_doors],
            "shuffle_royals": plan.shuffle_royals,
            "sticker_policy": asdict(plan.sticker_policy) if plan.sticker_policy else None,
            "vanilla_generic_stickers": plan.vanilla_generic_stickers,
            "scene_skips": [asdict(scene) for scene in plan.scene_skips],
            "presentation": {
                "skip_opening": plan.skip_opening,
                "skip_safe_scene_intervals": plan.skip_opening,
                "skip_royal_intermission_timelines": plan.skip_opening,
                "skip_dialogue": plan.skip_dialogue,
                "gameplay_verified": False,
            },
            "startup": {
                "post_tutorial_world_map": plan.ability_mode,
                "grants_shuffled_abilities": False,
                "gameplay_verified": False,
            },
            "remote_rewards": [asdict(entry) for entry in plan.remote_rewards],
            "remote_session": asdict(plan.remote_session) if plan.remote_session else None,
            "peeled_scrap_sources": [asdict(observed_source) for _, _, observed_source in peel_checks],
            "container_sources": [
                asdict(native_containers[(check.map_name, check.object_name)]) for check in container_checks
            ],
            "saved_byte_mailbox": plan.saved_byte_mailbox,
            "priority_pages": plan.priority_pages,
            "priority_capabilities": plan.priority_pages,
            "allocated_saved_bytes": [asdict(slot) for slot in saved_allocated],
            "rpc_memory_profile": rpc_profile,
            "code_patch": (
                {
                    "source_sha256": code_patch.source_sha256,
                    "patched_sha256": code_patch.patched_sha256,
                    "signatures": code_patch.signatures,
                }
                if code_patch
                else None
            ),
            "suppressed_vanilla_page_grants": suppressed_pages,
            "checks": [asdict(check) for check in plan.checks],
            "allocated_flags": [asdict(flag) for flag in allocated],
            "check_flags": [
                {
                    "id": check.id,
                    "checked": flag_indices[plan.receipt(index)[0]],
                    "delivered": (
                        None
                        if check.reward.kind in {NativeRewardKind.REMOTE, NativeRewardKind.EVENT}
                        else flag_indices[plan.receipt(index)[1]]
                    ),
                }
                for index, check in enumerate(plan.checks)
            ],
            "source_map_scripts": sorted(sources),
            "script_event_hooks": sorted(hooked_scripts),
            "enemy_victory_hooks": [check.id for _, check in enemy_checks],
            "script_hashes": emitted,
            "switch_source_sha256": hashlib.sha256(switch_source).hexdigest(),
            "switch_patched_sha256": hashlib.sha256(switch_patch).hexdigest(),
        }
        (staging / "patch-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (staging / "README.txt").write_text(
            "Native check/reward hook experiment. Emulator validation pending.\n"
            "Install the romfs folder and exefs folder (when present) together\n"
            "in a separate test profile and use a new save.\n"
            "Configured source stars grant their assigned reward, not their original route.\n"
            "Unconfigured sources retain vanilla behavior. Pending items retry on map entry\n"
            "and every 30 frames in maps using the common layout helper.\n"
            "Decalburg's custom initialization also runs the delivery poll.\n"
            "Sticker unlocks/copies, gated generic shops and Thing-shop unlocks are\n"
            "included when explicitly configured. A bound RPC mailbox supports the\n"
            "separate native AP client. Royal shuffle suppresses observed vanilla grants.\n"
            "Configured ability ownership filters native accessory attachments.\n"
            "Enemy death hooks commit checks only after an actual battle victory.\n"
            "Complete access logic, door/boss gates, remaining enemy callbacks,\n"
            "all custom map coverage and actual save/reload verification remain pending.\n",
            encoding="utf-8",
        )
        if output.exists() or output.is_symlink():
            raise FileExistsError("Output appeared while building")
        publish_directory(staging, output)
    return output

"""One persistent KSM engine backed by the expanded native variable arena."""

from .native_delivery import DeliveryPlan, EnemyReward
from .mailbox import remote_function
from .peels import peel_runtime
from .containers import container_runtime
from .things import thing_state_functions

RUNTIME_SCRIPT = "Script/ksm_item.bin"
VARIABLE_POOL_LIMIT = 0x6000


def item_grant_function() -> str:
    # false tests placement; true commits through the native item dispatcher.
    # A failed fit leaves the receipt pending and never invokes forced insertion.
    return """
private rando_item_grant(temp tempVar0)  {
\ttemp tempVar1 = item_try_addpouch*(tempVar0, false);
\tif ( tempVar1 ) {
\t\ttempVar1 = item_try_addpouch*(tempVar0, true);
\t}
\treturn* tempVar1;
}
"""


def shared_imports() -> dict[str, str]:
    # Original public KSM functions use the same name buckets as native imports.
    names = (
        "rando_seed_valid",
        "rando_deliver",
        "rando_royal_gate_count",
        "rando_enemy_mark",
        "rando_enemy_get",
        "rando_enemy_reset",
        "rando_peel_collect",
        "rando_peel_collect_selected",
        "rando_peel_can_return",
        "rando_peel_cancel",
        "rando_container_collect",
        "rando_thing_source_collected",
    )
    return {name: f"#import function {name} from 0x{sum(map(ord, name[len(name) // 2 :])) & 511:x} {{0x0}};" for name in names}


def runtime_functions(plan: DeliveryPlan) -> str:
    guard = (
        "\tlocal localVar99 = rando_peel_return_pending*();\n\tif ( localVar99 == false ) {\n\t\treturn*;\n\t}\n"
        if peel_runtime(plan)
        else ""
    )
    source = "\npublic rando_deliver()  {\n" + guard + plan.delivery_body() + "\n}\n"
    source += "\n" + plan.seed_function().replace("private rando_seed_valid", "public rando_seed_valid", 1)
    source += item_grant_function()
    if plan.enemy_pending_flags:
        source += "\npublic rando_enemy_mark(temp tempVar0)  {\n"
        for index, check in enumerate(plan.checks):
            if isinstance(check, EnemyReward):
                source += f"\tif ( tempVar0 == {index} ) {{\n\t\t{plan.enemy_pending(index)} = true;\n\t\treturn*;\n\t}}\n"
        source += "}\npublic rando_enemy_get(temp tempVar0)  {\n"
        for index, check in enumerate(plan.checks):
            if isinstance(check, EnemyReward):
                source += f"\tif ( tempVar0 == {index} ) {{\n\t\treturn* {plan.enemy_pending(index)};\n\t}}\n"
        source += "\treturn* false;\n}\npublic rando_enemy_reset()  {\n"
        source += "".join(f"\t{flag} = false;\n" for flag in plan.enemy_pending_flags) + "}\n"
    if plan.shuffle_royals:
        source += (
            "\npublic rando_royal_gate_count()  {\n\ttemp tempVar0 = rando_seed_v"
            "alid*();\n\tif ( tempVar0 == false ) {\n\t\treturn* 0;\n\t}\n\ttempVar0 = "
            "0;\n"
        )
        for index in range(1, 6):
            source += f"\tif ( gf_rando_royal_{index} ) {{\n\t\ttempVar0 = tempVar0 + 1;\n\t}}\n"
        source += "\treturn* tempVar0;\n}\n"
    if plan.page_flags:
        source += "\n" + plan.page_function()
    if plan.remote_rewards:
        source += remote_function(
            plan.remote_rewards,
            plan.shuffle_royals,
            plan.sticker_policy,
            plan.starting_item_ids,
            plan.starting_flags,
            plan.saved_byte_mailbox,
            plan.priority_pages,
        )
    source += peel_runtime(plan)
    source += container_runtime(plan)
    source += thing_state_functions(plan)
    if plan.priority_pages:
        source += "\nprivate rando_remote_page() {\n"
        for index, flag in enumerate(plan.remote_page_flags):
            source += f"\tif ( gs_rando_rpc_page_rank_00 == {index} && {flag} ) {{\n\t\treturn* true;\n\t}}\n"
        source += "\ttemp tempVar0 = rando_page_grant*();\n\treturn* tempVar0;\n}\n"
    return source

"""Language-independent overrides of native presentation entry points.

These transformations retain message-seen flags and surrounding game logic.
Menu/choice behavior and scene transitions require gameplay validation.
"""

from .script_build import replace_body

OPENING_SCRIPT = "Script/Opening/evt_Opening.bin"
MESSAGE_SCRIPT = "Script/ksm_msg.bin"


def skip_opening(source: str) -> str:
    # op_all is the visual timeline. init_default's surrounding setup/cleanup
    # remains intact, and no progression flags are fabricated by this patch.
    return replace_body(source, "op_all", "\treturn*;")


def skip_dialogue(source: str) -> str:
    source = replace_body(source, "msg_skip_start", "\tmsg_skip_setting*(true);")
    return replace_body(
        source, "msg_skip_end", "\tif ( localVar0 != -1 ) {\n\t\tlocalVar0 = true;\n\t}\n\tmsg_skip_setting*(true);"
    )

"""Language-independent overrides of native presentation entry points.

These transformations retain message-seen flags and surrounding game logic.
Menu/choice behavior and scene transitions require gameplay validation.
"""

import re

from .script_build import replace_body

OPENING_SCRIPT = "Script/Opening/evt_Opening.bin"
MESSAGE_SCRIPT = "Script/ksm_msg.bin"
BOSS_PRESENTATION_SCRIPT = "Script/ksm_other.bin"


def skip_opening(source: str) -> str:
    # op_all is the visual timeline. init_default's surrounding setup/cleanup
    # remains intact, and no progression flags are fabricated by this patch.
    return replace_body(source, "op_all", "\treturn*;")


def skip_dialogue(source: str) -> str:
    source = replace_body(source, "msg_skip_start", "\tmsg_skip_setting*(true);")
    return replace_body(
        source, "msg_skip_end", "\tif ( localVar0 != -1 ) {\n\t\tlocalVar0 = true;\n\t}\n\tmsg_skip_setting*(true);"
    )


def skip_boss_intros(source: str) -> str:
    """Use the original safe interval and cleanup callback, including first visits.

    The caller marks only the skippable portion with localVar1. Initialization
    and battle setup outside that interval must finish normally. A missing
    cleanup callback leaves the scene intact rather than deleting its thread.
    """
    return replace_body(source, "boss_skip", """\ttemp tempVar0;
\tlabel0:
\ttempVar0 = is_incomplete localVar2;
\tif ( tempVar0 == false ) {
\t\treturn*;
\t}
\tif ( localVar1 && localVar3 != 0 ) {
\t\tdelete localVar2;
\t\tlocalVar3();
\t\treturn*;
\t}
\tsleep_frames* 1;
\tgoto label0;""")


def skip_royal_intermission(source: str, world: int) -> str:
    """Bypass the visual timeline, retaining grants, book cleanup and exit."""
    if type(world) is not int or not 1 <= world <= 5:
        raise ValueError("Expected one of the five native Royal intermissions")
    if source.count("private finish_itm(") != 1:
        raise ValueError("Expected one original intermission completion function")
    start = source.index("private finish_itm(")
    end = source.find("\nprivate ", start + 1)
    if end < 0:
        raise ValueError("Intermission completion layout no longer matches the original")
    finish = source[start:end]
    for pattern in (
        r"\bui_msgbox_addpage\*?\(\);",
        r"\bsub_wait_pad_get_trigger\*?\(pad_button_a\);",
        r"\bui_msgbox_clear\*?\(\);",
    ):
        finish, count = re.subn(pattern, "", finish)
        if count != 1:
            raise ValueError("Intermission page notification no longer matches the original")
    source = source[:start] + finish + source[end:]
    return replace_body(source, "enter_event", (
        "\tmap_set_anime_step*(0);\n\tmap_wait_run_init_script*();\n"
        f"\tfinish_itm*(pouch_royal_w{world});"
    ))

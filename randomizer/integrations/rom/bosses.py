"""Separate received boss admission from native boss/story completion."""

from dataclasses import dataclass
import re

from .script_build import prepend_body


@dataclass(frozen=True)
class BossGate:
    code: str
    script_file: str
    callback: str
    case_name: str = ""
    case_callback: str = ""
    registrations: int = 0


BOSS_GATES = {
    "w1": BossGate("w1", "Script/Map/IWA/iwa_2_10.bin", "main_kuriboo_boss16", "a_event001", "main_kuriboo_boss16", 4),
    "w2": BossGate("w2", "Script/Map/W2_TOW/w2_tow_15.bin", "boss_sambo_main", "af_event001", "boss_sambo_main", 3),
    "w3": BossGate("w3", "Script/Map/W3_BOS/w3_bos_03.bin", "boss_main", "af_event001", "boss_main", 2),
    "w4": BossGate("w4", "Script/Map/W4_BOS/w4_bos_00.bin", "boss_battle_main", "a_event001", "boss_battle_main_under", 1),
    "w5": BossGate("w5", "Script/Map/W5_BOS/w5_bos_01.bin", "boss_packun_main", "af_event003", "boss_packun_main", 1),
    "w6": BossGate("w6", "Script/Map/W6_BOS/w6_bos_04.bin", "koopa_battle_event", "af_event001", "koopa_battle_event", 1),
    "harbor": BossGate("harbor", "Script/Map/MAC/mac_2_02.bin", "action_dekapuku"),
}


def gate_boss(source: str, gate: BossGate, require_royals: bool = False) -> str:
    owned = f"gf_rando_boss_{gate.code}"
    guard = (
        f"\ttemp tempVar90 = rando_seed_valid*();\n\tif ( tempVar90 == false || {owned} == false ) {{\n\t\treturn*;\n\t}}\n"
    )
    if require_royals and gate.code == "w6":
        guard += "\ttemp tempVar91 = rando_royal_gate_count*();\n\tif ( tempVar91 < 5 ) {\n\t\treturn*;\n\t}\n"
    source = prepend_body(source, gate.callback, guard)
    if not gate.case_name:
        return source
    pattern = (
        r'\bcase_entry_detail\*?\("' + re.escape(gate.case_name) + r'", "' + re.escape(gate.case_callback) + r'", [^\n]*\);'
    )
    source, count = re.subn(pattern, lambda match: match.group() + "\n\trando_boss_admission*();", source)
    if count != gate.registrations:
        raise ValueError("Boss trigger registration no longer matches the inspected revision")
    if gate.code == "w4":
        # The upper entry starts a fight automatically. When locked, retain the
        # existing non-boss coaster arrival path, which restores player control.
        start = source.index("private n_bero3_enter_evt(")
        end = source.find("\nprivate ", start + 1)
        if end < 0:
            end = len(source)
        section = source[start:end]
        if section.count("if ( tempVar3 )") != 1:
            raise ValueError("Snow boss upper arrival no longer matches its native control flow")
        source = source[:start] + section.replace("if ( tempVar3 )", f"if ( tempVar3 && {owned} )") + source[end:]
    source = prepend_body(source, "init", "\tthread rando_boss_poll*();\n")
    pending = f"gf_rando_boss_pending_{gate.code}"
    royal_query = "\ttemp tempVar1 = rando_royal_gate_count*();\n" if require_royals and gate.code == "w6" else ""
    royal_condition = " || tempVar1 < 5" if royal_query else ""
    source += f"""
private rando_boss_admission()  {{
\ttemp tempVar0 = rando_seed_valid*();
\tif ( tempVar0 == false ) {{
\t\tcase_cancel*("{gate.case_name}", "{gate.case_callback}");
\t\treturn*;
\t}}
{royal_query}\tif ( {owned} == false{royal_condition} ) {{
\t\tcase_cancel*("{gate.case_name}", "{gate.case_callback}");
\t\t{pending} *= true;
\t}} else {{
\t\tif ( {pending} ) {{
\t\t\tcase_uncancel*("{gate.case_name}", "{gate.case_callback}");
\t\t\t{pending} *= false;
\t\t}}
\t}}
}}
private rando_boss_poll()  {{
\twhile* 1 {{
\t\trando_boss_admission*();
\t\tsleep_frames* 30;
\t}}
}}
"""
    return source

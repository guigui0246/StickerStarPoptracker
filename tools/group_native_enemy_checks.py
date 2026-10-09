"""Group selected native enemy variants before seed placement.

Reads your own extracted battle table and an explicit native plan. The plan
must not assign conflicting rewards to variants of the same enemy type.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from randomizer.integrations.rom.enemies import enemy_types, group_enemy_checks
from randomizer.integrations.rom.native_delivery import EnemyReward, NativeRewardKind
from randomizer.integrations.rom.plan_io import decode_plan, encode_plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--battle-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new output file")
    plan = decode_plan(json.loads(args.plan.read_text(encoding="utf-8")))
    native = enemy_types(args.battle_data.read_bytes())
    by_unit = {enemy.unit_id: enemy for enemy in native}
    selected = tuple(check for check in plan.checks if isinstance(check, EnemyReward))
    props = tuple(
        check for check in selected if any(by_unit[hook.unit_id].name_label == "enemy_name_DOOR" for hook in check.hooks)
    )
    # Dropping a placed progression reward is never an implicit operation.
    if any(check.reward.kind != NativeRewardKind.REMOTE for check in props):
        parser.error("Remove prop checks before placement; their local rewards cannot be discarded")
    grouped = group_enemy_checks(native, tuple(check for check in selected if check not in props))
    checks = tuple(check for check in plan.checks if not isinstance(check, EnemyReward)) + grouped
    result = replace(plan, checks=checks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(encode_plan(result), stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "selected_unit_checks": len(selected),
                "global_enemy_type_checks": len(grouped),
                "excluded_prop_checks": [check.id for check in props],
                "total_checks": len(result.checks),
                "save_bits": len(result.flags),
                "complete_game_catalog": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

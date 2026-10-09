from dataclasses import replace
import unittest

from ..integrations.rom.native_delivery import DeliveryPlan, NativeReward, NativeRewardKind, PickupReward
from ..integrations.rom.things import (
    FAUCET_EFFECT_SCRIPTS,
    SCRIPTED_THING_SCRIPTS,
    THING_INITIALIZER_CALLERS,
    hook_thing_effects,
    hook_thing_initialization,
    scripted_things,
    thing_state_functions,
    thing_effect_scripts,
)


class ThingSourceTests(unittest.TestCase):
    def plan(self):
        return DeliveryPlan(
            (
                PickupReward("hei_2_04", "item_bibcock", "REAL_TAP", NativeReward(NativeRewardKind.COINS, 25)),
                PickupReward("w4_kaw_00", "realobj001", "REAL_CURLING_STONE", NativeReward(NativeRewardKind.COINS, 25)),
            )
        )

    def test_faucet_source_requires_the_actual_acquisition_actor(self):
        source = (
            'private init() { var_0x123 *= "bibcock"; item_static_entry*(var_0'
            'x123, "REAL_TAP", 0, -1000, 0); }\nprivate get() {\nlocal localVar5'
            ' *= "item_bibcock";\nitem_static_entry*(localVar5, "REAL_TAP", 0, '
            "-1000, 0);\nitem_get_evt_real*(localVar5);\n}\n"
        )
        (item,) = scripted_things("hei_2_04", source)
        self.assertEqual(item.object_name, "item_bibcock")
        self.assertEqual(item.display_objects, ("bibcock",))
        with self.assertRaises(ValueError):
            scripted_things("hei_2_04", source.replace("item_get_evt_real*(localVar5)", "item_get_evt_real*(localVar6)"))

    def test_ski_reward_table_and_thread_actor_must_agree(self):
        source = (
            'var_array evt_ski_arg_tbl = {1, "S_1", chars, 5, 100, "coins", re'
            'wards, "reward", "REAL_CURLING_STONE", "real", 90.0, 60.0, "curve'
            '"};\n'
            'array_copy_1(tempVar0, 8, var_0x123);\nvar_0x456 *= "realobj001";\n'
            "thread init[var_0x456 -> temp tempVar0] { item_static_entry*(tempVar0, var_0x123, 0, -1000, 0); }\n"
            "item_get_real_name*(tempVar1);\n"
        )
        (item,) = scripted_things("w4_kaw_00", source)
        self.assertEqual(item.source_item, "REAL_CURLING_STONE")
        with self.assertRaises(ValueError):
            scripted_things("w4_kaw_00", source.replace('"REAL_CURLING_STONE"', '"REAL_FAN"'))
        with self.assertRaises(ValueError):
            scripted_things("w4_kaw_00", source.replace("var_0x456 ->", "var_0x789 ->"))

    def test_source_visibility_uses_collection_even_when_its_reward_is_remote(self):
        plan = self.plan()
        local = thing_state_functions(plan)
        remote = thing_state_functions(
            replace(
                plan, checks=tuple(replace(check, reward=NativeReward(NativeRewardKind.REMOTE, 2)) for check in plan.checks)
            )
        )
        self.assertEqual(local, remote)
        self.assertIn("return* gf_rando_check_0000", local)
        self.assertNotIn("gf_rando_delivered", local)
        self.assertIn('tempVar0 == "bibcock"', local)
        self.assertIn("localVar1 = item_check_pouch*(tempVar1, true)", local)
        original = (
            "public real_obj_init(temp tempVar0, temp tempVar1) {\ntemp tempVar"
            "3 = item_get_item_id*(tempVar0);\nif ( item_check_pouch*(tempVar3,"
            " true) ) { character_hide*(tempVar0); }\ncase_entry_detail*(tempVa"
            "r0);\n}\n"
        )
        patched = hook_thing_initialization(original)
        self.assertIn("rando_thing_owned*(tempVar0, tempVar3)", patched)
        self.assertIn("case_entry_detail*(tempVar0)", patched)

    def test_water_effects_and_ski_spawn_do_not_follow_received_thing_ownership(self):
        plan = self.plan()
        water = (
            'private mizuhiki_check() {\nreturn item_check_pouch*("REAL_TAP", true);\n}\n'
            "private init() { original_water_mesh*(); }\n"
            "private bibcock_init() {\n\tif ( false == mizuhiki_check() ) {\n\t\toriginal_actor_entry*();\n\t}\n}\n"
        )
        for filename in FAUCET_EFFECT_SCRIPTS:
            patched = hook_thing_effects(water, filename, plan)
            self.assertIn("rando_thing_source_collected*(0)", patched)
            self.assertNotIn("item_check_pouch", patched)
            self.assertIn("original_water_mesh*()", patched)
            self.assertIn("local localVar91 = mizuhiki_check*();", patched)
            self.assertIn("if ( false == localVar91 )", patched)
            self.assertIn("original_actor_entry*()", patched)
        ski = (
            "array_copy_1(tempVar0, 8, var_0x123);\n"
            '\tif ( real_obj_init(tempVar0, "ski_real_get") ) { original_hit_shape*(); }\n'
            + "item_check_pouch*(var_0x123, true);\n"
            * 2
        )
        self.assertEqual(
            hook_thing_effects(ski, SCRIPTED_THING_SCRIPTS["w4_kaw_00"], plan).count("rando_thing_source_collected*(1)"), 2
        )

    def test_heater_prize_variants_keep_their_own_collection_identity(self):
        reward = NativeReward(NativeRewardKind.COINS, 25)
        plan = DeliveryPlan(
            (
                PickupReward("w3_bea_04", "real", "REAL_OIL_HEATER", reward),
                PickupReward("w3_bea_06", "real", "REAL_OIL_HEATER", reward),
            )
        )
        filename = "Script/Map/W3_BEA/w3_bea_06.bin"
        source = (
            'private init() {\n\tif ( item_check_pouch("REAL_OIL_HEATER", true) '
            "== false ) {\n\t\toriginal_heat_effect*();\n\t}\n}\n"
        )
        patched = hook_thing_effects(source, filename, plan)
        self.assertIn("rando_thing_source_collected*(1)", patched)
        self.assertNotIn("rando_thing_source_collected*(0)", patched)
        self.assertIn("original_heat_effect*()", patched)
        self.assertIn("if ( localVar90 == false )", patched)
        self.assertIn(filename, thing_effect_scripts(plan))

    def test_partial_thing_plans_preserve_all_shared_initializer_callers(self):
        plan = DeliveryPlan((self.plan().checks[0],))
        self.assertTrue(set(THING_INITIALIZER_CALLERS) <= set(thing_effect_scripts(plan)))
        filename = "Script/Map/W4_YUK/w4_yuk_04.bin"
        original = (
            'private init() {\n\tif ( real_obj_init("real_goat", "goat_get") ) {\n\t\toriginal_goat_hit_shape*();\n\t}\n}\n'
        )
        patched = hook_thing_effects(original, filename, plan)
        self.assertIn('real_obj_init*("real_goat", "goat_get")', patched)
        self.assertIn("original_goat_hit_shape*()", patched)
        self.assertNotIn("if ( real_obj_init", patched)
        with self.assertRaises(ValueError):
            hook_thing_effects(original + original, filename, plan)
        non_thing = DeliveryPlan((replace(plan.checks[0], source_item="PK_FIELD_HEI_2_GOAL_STAR"),))
        self.assertEqual(thing_effect_scripts(non_thing), ())


if __name__ == "__main__":
    unittest.main()

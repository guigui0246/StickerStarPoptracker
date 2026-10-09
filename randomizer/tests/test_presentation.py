import unittest

from ..integrations.rom.presentation import skip_boss_intros, skip_dialogue, skip_opening, skip_royal_intermission


class PresentationTests(unittest.TestCase):
    def test_intermission_skip_preserves_rewards_cleanup_and_exit(self) -> None:
        source = (
            "private finish_itm(local localVar0)  {\n"
            '\titem_try_addpouch*("SL_PAGE", true);\n\tpouch_set_royal_seal*(localVar0);\n'
            "\tui_msgbox_addpage*();\n\tsub_wait_pad_get_trigger*(pad_button_a);\n\tui_msgbox_clear*();\n"
            '\tui_end_sealbook_cover*();\n\tmap_exit*("royal");\n}\n'
            'private royal_exit()  {\n\tplayer_restart*("mario");\n}\n'
            "private enter_event()  {\n\tthread movie*();\n\tsleep_frames* 450;\n}\n"
        )
        result = skip_royal_intermission(source, 3)
        self.assertIn('item_try_addpouch*("SL_PAGE", true)', result)
        self.assertIn("pouch_set_royal_seal*(localVar0)", result)
        self.assertIn('map_exit*("royal")', result)
        self.assertIn("ui_end_sealbook_cover", result)
        self.assertIn("finish_itm*(pouch_royal_w3)", result)
        self.assertNotIn("thread movie", result)
        self.assertNotIn("sub_wait_pad", result)
        self.assertNotIn("ui_msgbox", result)

    def test_scene_skip_requires_safe_interval_and_cleanup_and_keeps_other_functions(self) -> None:
        source = (
            "public boss_skip(local localVar0, local ref localVar1, local localVar2, local localVar3)  {\n"
            "\tif ( localVar0 != 0 ) {\n\t\tsub_pad_get_press*(pad_button_start);\n\t}\n}\n"
            "public battle()  {\n\tnpc_call_battle*(enemy, setup_normal);\n}\n"
        )
        result = skip_boss_intros(source)
        self.assertIn("if ( localVar1 && localVar3 != 0 )", result)
        self.assertIn("is_incomplete localVar2", result)
        self.assertIn("sleep_frames* 1", result)
        self.assertLess(result.index("delete localVar2"), result.index("localVar3();"))
        self.assertNotIn("sub_pad_get_press", result)
        self.assertNotIn("localVar0 != 0", result)
        self.assertEqual(result.split("public battle", 1)[1], source.split("public battle", 1)[1])

    def test_opening_removes_only_visual_timeline_and_keeps_surrounding_setup(self):
        source = (
            "private op_all(temp tempVar0)  {\n\tthread visual*();\n\tsleep_frames"
            "* 400;\n}\nprivate init_default(temp tempVar0)  {\n\tbgm_stop*(0);\n\to"
            "p_all*(tempVar0);\n\tbgm_stop*(0);\n}\n"
        )
        result = skip_opening(source)
        self.assertIn("return*;", result)
        self.assertNotIn("sleep_frames", result)
        self.assertEqual(result.split("private init_default", 1)[1], source.split("private init_default", 1)[1])

    def test_dialogue_preserves_seen_flag_and_other_functions(self):
        source = (
            "public msg_skip_start(temp tempVar0)  {\n\tmsg_skip_setting*(tempVa"
            "r0);\n}\npublic msg_skip_end(local ref localVar0)  {\n\tlocalVar0 = t"
            "rue;\n\tmsg_skip_setting*(false);\n}\npublic choice()  {\n\treturn* men"
            "u*();\n}\n"
        )
        result = skip_dialogue(source)
        self.assertIn("localVar0 = true", result)
        self.assertIn("if ( localVar0 != -1 )", result)
        self.assertEqual(result.count("msg_skip_setting*(true)"), 2)
        self.assertEqual(result.split("public choice", 1)[1], source.split("public choice", 1)[1])


if __name__ == "__main__":
    unittest.main()

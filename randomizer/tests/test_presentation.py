import unittest

from ..integrations.rom.presentation import skip_dialogue, skip_opening


class PresentationTests(unittest.TestCase):
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

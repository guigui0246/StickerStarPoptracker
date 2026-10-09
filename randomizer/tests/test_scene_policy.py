import unittest

from ..integrations.rom.scene_policy import SceneSkip, skip_scene


class ScenePolicyTests(unittest.TestCase):
    def test_cleanup_preserves_other_functions_and_rejects_gameplay_hook_erasure(self) -> None:
        scene = SceneSkip("Script/Map/ROOM/room.bin", "timeline", "finish")
        original = "private timeline() {\nwait_visual();\n}\nprivate finish() {\nset_story();\n}\n"
        result = skip_scene(original, scene)
        self.assertIn("finish*();", result)
        self.assertIn("set_story();", result)
        self.assertNotIn("wait_visual", result)
        with self.assertRaises(ValueError):
            skip_scene(original.replace("wait_visual();", "rando_deliver*();"), scene)
        with self.assertRaises(ValueError):
            skip_scene(original.replace("finish()", "finish(local arg)"), scene)
        with self.assertRaises(ValueError):
            SceneSkip("../outside.bin", "timeline", "finish")

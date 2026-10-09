import unittest

from ..integrations.rom.royal_patch import shuffled_royal_gate


class RoyalGateTests(unittest.TestCase):
    def test_only_expected_native_royal_count_calls_are_replaced(self) -> None:
        source = "\n".join(
            f"private gate{index}()  {{\n\ttemp tempVar0 = pouch_get_royal_seal_num*();\n\toriginal_event*();\n}}"
            for index in range(4)
        )
        result = shuffled_royal_gate(source)
        self.assertEqual(result.count("rando_royal_gate_count*()"), 4)
        self.assertEqual(result.count("original_event*()"), 4)
        with self.assertRaises(ValueError):
            shuffled_royal_gate(source + "\npouch_get_royal_seal_num*();")

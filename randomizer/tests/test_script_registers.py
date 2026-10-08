import unittest

from ..integrations.rom.script_build import lower_temporary_registers


class ScriptRegisterTests(unittest.TestCase):
    def test_injected_scratch_uses_free_locals_and_preserves_literals(self) -> None:
        source = '''public actor(temp tempVar0)  {
\tlocal localVar0 = 1;
\ttemp tempVar90 = helper*();
\ttemp tempVar91 = tempVar90;
\tmessage*("tempVar90 { escaped \\\" quote }");
\tif ( tempVar91 ) { tempVar0 = localVar0; }
}
private other()  { temp tempVar95 = helper*(); }
'''
        result = lower_temporary_registers(source)
        self.assertIn("local localVar255 = helper*()", result)
        self.assertIn("local localVar254 = localVar255", result)
        self.assertIn("if ( localVar254 ) { tempVar0 = localVar0; }", result)
        self.assertIn('message*("tempVar90 { escaped', result)
        self.assertIn("private other()  { local localVar255 = helper*(); }", result)
        self.assertEqual(lower_temporary_registers(result), result)

    def test_native_formal_arguments_cannot_exceed_the_twenty_register_bank(self) -> None:
        with self.assertRaises(ValueError):
            lower_temporary_registers("public bad(temp tempVar20)  { return*; }")
        source = "public valid(temp tempVar19)  { temp tempVar0 = tempVar19; }"
        self.assertEqual(lower_temporary_registers(source), source)

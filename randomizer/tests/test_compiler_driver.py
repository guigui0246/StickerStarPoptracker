import unittest
import struct
from unittest.mock import Mock

from ..integrations.rom.compiler_driver import hoist_literal_arrays, read_literal, read_instruction
from ..integrations.rom.script_build import validate_function_contracts, validate_runtime_calls


class CompilerDriverTests(unittest.TestCase):
    def test_compiler_cannot_keep_a_helper_definition_but_drop_its_calls(self):
        source = "private rando_query() {\n}\nprivate init() {\nlocal localVar0 = rando_query*();\n}\n"
        validate_runtime_calls(source, source.replace("rando_query*()", "rando_query()"))
        with self.assertRaises(ValueError):
            validate_runtime_calls(source, source.replace("local localVar0 = rando_query*();", "local localVar0 = false;"))

    def test_native_infinities_preserve_ieee_bits_and_lexer_position(self):
        original = Mock()
        reader = Mock(term="inf", line=", 0};")
        value, kind = read_literal(reader, original)
        self.assertEqual((struct.pack("<f", value), kind), (bytes.fromhex("0000807f"), "float"))
        reader = Mock(term="-", line="inf, 0};")
        value, kind = read_literal(reader, original)
        self.assertEqual((struct.pack("<f", value), kind), (bytes.fromhex("000080ff"), "float"))
        reader.getNextTerm.assert_called_once_with()
        original.assert_not_called()
        source = "private init() { use*(curve); }\nvar_array curve = {inf, -inf, 0.0};\n"
        self.assertTrue(hoist_literal_arrays(source).startswith("var_array curve"))

    def test_forward_literal_arrays_keep_values_and_function_source(self):
        source = (
            'private init()  {\n\tarray_copy_1(table, 0, tempVar0);\n}\nvar_array table = {0, -2, 1.25, true, "a,b", 0xAB};\n'
        )
        result = hoist_literal_arrays(source)
        self.assertTrue(result.startswith('var_array table = {0, -2, 1.25, true, "a,b", 0xAB};'))
        self.assertEqual(result.count("var_array table"), 1)
        self.assertIn(source.split("var_array", 1)[0], result)

    def test_computed_and_local_arrays_are_not_moved(self):
        source = "var_array table = {variable, 2};\nprivate init()  {\n\tvar_array local_table = {1, 2};\n}\n"
        self.assertEqual(hoist_literal_arrays(source), source)

    def test_header_slot_arrays_keep_references(self):
        source = "private init()  {\n\tarray_assign_1(table, 0, 2);\n}\nvar_array table = {var_0x30012345, 0};\n"
        self.assertTrue(hoist_literal_arrays(source).startswith("var_array table = {var_0x30012345, 0};"))

    def test_compilation_cannot_drop_callbacks_or_change_public_scope(self):
        source = "public entry()  {\n}\nprivate callback()  {\n}\n"
        validate_function_contracts(source, source)
        with self.assertRaises(ValueError):
            validate_function_contracts(source, "public entry()  {\n}\n")
        with self.assertRaises(ValueError):
            validate_function_contracts(source, source.replace("public entry", "private entry"))

    def test_digit_prefixed_native_identifiers_are_not_rewritten_as_numbers(self):
        for token in ("16mai_kuriboo_parts_damage", "2mai_kuriboo", "10mai_heihoo"):
            original = Mock()
            self.assertEqual(read_literal(Mock(term=token), original), (None, None))
            original.assert_not_called()

    def test_actual_literals_and_other_tokens_keep_original_parser_behavior(self):
        for token in ("16", "0xABCD", "0x0", "1.25", "true", '"16mai_kuriboo"', "identifier", "-"):
            reader = Mock(term=token, line="")
            original = Mock(return_value=(42, "int"))
            self.assertEqual(read_literal(reader, original, True), (42, "int"))
            original.assert_called_once_with(reader, True)

    def test_digit_prefixed_calls_preserve_parser_state_and_use_call_opcode(self):
        reader = Mock(term="16mai_kuriboo_parts_damage", line="*(self);")
        original = Mock(return_value="assignment")
        call = Mock(return_value="call")
        self.assertEqual(read_instruction(reader, None, original, call, True), "call")
        original.assert_called_once_with(reader, None, True)
        call.assert_called_once_with()
        reader.term = "16"
        call.reset_mock()
        self.assertEqual(read_instruction(reader, None, original, call), "assignment")
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()

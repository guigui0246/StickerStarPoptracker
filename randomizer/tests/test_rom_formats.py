from typing import Any, cast
import struct
import unittest
from unittest.mock import Mock, patch

from ..integrations.citra.memory import CitraMemory, CitraProtocolError, RequestType
from ..integrations.rom.kdm import KdmDocument, KdmPointer
from ..integrations.rom.compression import decompress_code
from ..integrations.rom.ksm import KsmDocument


def small_kdm() -> bytes:
    header = b"KDMR\x00\x01\x01\x00" + struct.pack("<8I", 10, 15, 16, 17, 18, 25, 31, 37)
    strings = struct.pack("<I", 3) + b"A\0\0\0B\0\0\0Table\0\0\0"
    empty_sections = bytes(12)
    definition = struct.pack("<IHH5I", 1, 21, 3, 0, 0, 3, 8, 3)
    data = struct.pack("<I4HIH2xI", 1, 22, 3, 21, 3, 44, 7, 48)
    tables = struct.pack("<II4HII", 1, 52, 23, 2, 15, 2, 112, 0)
    return header + strings + empty_sections + definition + data + tables + bytes(4)


class KdmTests(unittest.TestCase):
    def test_packed_structures_and_pointer_tables(self) -> None:
        source = small_kdm()
        document = KdmDocument(source)
        reference = document.tables["Table"].values[0].value
        self.assertIsInstance(reference, KdmPointer)
        row = document.pointed_array(cast(Any, reference)).values[0]
        self.assertEqual(tuple(field.value for field in cast(Any, row).value), ("A", 7, "B"))
        self.assertEqual(tuple(field.offset for field in cast(Any, row).value), (112, 116, 120))
        self.assertEqual(document.edit_strings({}), source)
        changed = document.edit_strings({112: "B"})
        self.assertEqual(len(changed), len(source))
        self.assertEqual(changed[:112], source[:112])
        self.assertEqual(changed[116:], source[116:])
        self.assertEqual(cast(Any, KdmDocument(changed).arrays[112].values[0]).value[0].value, "B")

    def test_edits_reject_unregistered_fields_and_strings(self) -> None:
        document = KdmDocument(small_kdm())
        for replacements in ({116: "B"}, {112: "Missing"}, {0: "B"}):
            with self.assertRaises(ValueError):
                document.edit_strings(replacements)
        with self.assertRaises(ValueError):
            KdmDocument(small_kdm()[:-8])

    def test_bad_compression_cannot_allocate_unbounded_output(self) -> None:
        with self.assertRaises(ValueError):
            decompress_code(b"12345678")
        with self.assertRaises(ValueError):
            decompress_code(struct.pack("<2I", 0x08000008, 0xFFFFFFFF))


class KsmTests(unittest.TestCase):
    def test_lossless_constants_and_native_imports(self) -> None:
        header = b"KSMR" + struct.pack("<I8II", 0x10300, 11, 14, 15, 16, 17, 25, 35, 36, 0)
        metadata_and_empty_sections = bytes(24)
        constant = struct.pack("<6I", 1, 0, 0x40000001, 3, 0, 2) + b"SL_JUMP\0"
        imports = struct.pack("<9I", 1, 0xFFFFFFFF, 0x880003, 7, 0, 0xA1, 0, 0, 1) + b"f\0\0\0"
        source = header + metadata_and_empty_sections + constant + imports + bytes(4) + struct.pack("<2I", 1, 0)
        document = KsmDocument(source)
        self.assertEqual(document.constants[0].value, "SL_JUMP")
        self.assertEqual(document.imports[0].name, "f")
        self.assertEqual(document.imports[0].file_id, 0x88)
        self.assertEqual(document.imports[0].uses, 3)
        self.assertEqual(document.replace_string_constants({}), source)
        changed = document.replace_string_constants({0x40000001: "SL_POW"})
        self.assertEqual(changed[:92], source[:92])
        self.assertEqual(changed[100:], source[100:])
        self.assertEqual(KsmDocument(changed).constants[0].value, "SL_POW")
        with self.assertRaises(ValueError):
            document.replace_string_constants({0x40000001: "TOO_LONG_FOR_SLOT"})
        with self.assertRaises(ValueError):
            document.replace_string_constants({0x40000002: "SL_POW"})


class CitraProtocolTests(unittest.TestCase):
    def test_chunked_reads_validate_ids_and_custom_port(self) -> None:
        fake = Mock()
        fake.recvfrom.side_effect = [
            (struct.pack("<4I", 1, 1, 1, 32) + b"a" * 32, ("127.0.0.1", 12345)),
            (struct.pack("<4I", 1, 1, 1, 3) + b"bbb", ("127.0.0.1", 12345)),
        ]
        with (
            patch("socket.socket", return_value=fake),
            patch("secrets.randbits", return_value=1),
        ):
            with CitraMemory(port=12345) as memory:
                self.assertEqual(memory.read(0x100000, 35), b"a" * 32 + b"bbb")
        requests = fake.sendto.call_args_list
        self.assertEqual(requests[0].args[1], ("127.0.0.1", 12345))
        self.assertEqual(struct.unpack("<2I", requests[1].args[0][16:]), (0x100020, 3))
        fake.close.assert_called_once()

    def test_bad_response_rejected_and_writes_chunked(self) -> None:
        fake = Mock()
        endpoint = ("127.0.0.1", 45987)
        fake.recvfrom.return_value = (struct.pack("<4I", 1, 1, 2, 0), endpoint)
        with (
            patch("socket.socket", return_value=fake),
            patch("secrets.randbits", return_value=1),
        ):
            with CitraMemory() as memory:
                memory.write(0x100000, bytes(50))
                self.assertEqual(
                    [len(call.args[0]) for call in fake.sendto.call_args_list],
                    [48, 48, 26],
                )
                with self.assertRaises(CitraProtocolError):
                    memory.request(RequestType.READ, bytes(8), 4)
                with self.assertRaises(ValueError):
                    memory.read(0xFFFFFFFF, 2)


if __name__ == "__main__":
    unittest.main()

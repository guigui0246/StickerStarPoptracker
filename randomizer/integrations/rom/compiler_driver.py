"""Run the external Gibberish compiler with a bounded lexer compatibility fix.

Native functions such as 16mai_kuriboo_parts_damage start with a digit. The
upstream lexer mistakes these identifiers for integers. Some original scripts
also reference literal global arrays before declaring them. This adapter fixes
these compiler boundaries without renaming functions or modifying the tool.
"""

from collections.abc import Callable
from pathlib import Path
import re
import runpy
import sys
from typing import Protocol, cast


class TokenReader(Protocol):
    term: str
    line: str
    def readConstValue(self, enforceUnsignedInt: bool = False) -> tuple[object, str | None]: ...


LiteralReader = Callable[[TokenReader, bool], tuple[object, str | None]]
InstructionReader = Callable[[TokenReader, object, bool], object]


def hoist_literal_arrays(source: str) -> str:
    """Predeclare arrays of literals/header slots for the single-pass reader."""
    literal = r'(?:var_0x[0-9a-fA-F]+|[-+]?(?:0x[0-9a-fA-F]+|[0-9]+(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?)|true|false|"(?:[^"\\]|\\.)*")'
    declarations: list[str] = []

    def select(match: re.Match[str]) -> str:
        values = match.group(1)
        if not re.fullmatch(r"\s*" + literal + r"(?:\s*,\s*" + literal + r")*\s*", values):
            return match.group()
        declarations.append(match.group())
        return ""

    remaining = re.sub(r"^var_array [A-Za-z_][A-Za-z0-9_]* = \{([^\n]*)\};[ \t]*$", select, source, flags=re.MULTILINE)
    return "\n".join(declarations) + "\n" + remaining if declarations else source


def digit_identifier(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9]\w+", token) and not re.fullmatch(r"[0-9]+|0x[0-9a-fA-F]+", token))


def read_literal(reader: TokenReader, original: LiteralReader, unsigned: bool = False) -> tuple[object, str | None]:
    token = reader.term
    if digit_identifier(token):
        return None, None
    return original(reader, unsigned)


def read_instruction(reader: TokenReader, data: object, original: InstructionReader, call: Callable[[], object], aligned: bool = False) -> object:
    result = original(reader, data, aligned)
    if reader.term and digit_identifier(reader.term) and re.match(r"^\s*\*?\s*\(", reader.line):
        return call()
    return result


def main() -> None:
    if len(sys.argv) != 3:
        raise ValueError("Expected external compiler and script paths")
    compiler = Path(sys.argv[1]).resolve(strict=True)
    script = Path(sys.argv[2]).resolve(strict=True)
    sys.path.insert(0, str(compiler.parent))
    namespace = runpy.run_path(str(compiler), run_name="gibberish_compiler")
    terms = sys.modules.get("gibberishModules.terms")
    if terms is None or not callable(namespace.get("main")):
        raise ValueError("Unsupported Gibberish compiler API")
    reader_class = cast(type[TokenReader], getattr(terms, "iterableFile"))
    original = reader_class.readConstValue
    def corrected(reader: TokenReader, enforceUnsignedInt: bool = False) -> tuple[object, str | None]:
        return read_literal(reader, original, enforceUnsignedInt)
    setattr(reader_class, "readConstValue", corrected)
    instructions = sys.modules["gibberishModules.instructions"]
    body = sys.modules["gibberishModules.cppbody"]
    original_instruction = cast(InstructionReader, getattr(instructions, "identifyInstructionFromCpp"))
    call = cast(Callable[[], object], getattr(instructions, "callInstruction"))
    def corrected_instruction(reader: TokenReader, data: object, aligned: bool = False) -> object:
        return read_instruction(reader, data, original_instruction, call, aligned)
    setattr(instructions, "identifyInstructionFromCpp", corrected_instruction)
    setattr(body, "identifyInstructionFromCpp", corrected_instruction)
    original_body_parser = cast(Callable[..., object], namespace["parseCppBodyFile"])
    def corrected_body_parser(source: list[str], *args: object) -> object:
        return original_body_parser(hoist_literal_arrays("".join(source)).splitlines(keepends=True), *args)
    main_globals = cast(dict[str, object], getattr(namespace["main"], "__globals__"))
    main_globals["parseCppBodyFile"] = corrected_body_parser
    sys.argv = [str(compiler), str(script)]
    cast(Callable[[], None], namespace["main"])()


if __name__ == "__main__":
    main()

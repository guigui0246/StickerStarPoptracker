"""Checked script transformations using the external Gibberish compiler."""

from dataclasses import dataclass
from collections import Counter
import hashlib
from pathlib import Path
import re

from .ksm import KsmDocument, KsmValueType
from .project import RomProject
from .tutorial_skip import compile_script


def prepend_body(source: str, name: str, body: str) -> str:
    matches = list(re.finditer(r"\b(?:public|private) " + re.escape(name) + r"\([^\n]*\)[^\n{]*\{", source))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one script function: {name}")
    start = matches[0].end()
    return source[:start] + "\n" + body + source[start:]


def replace_body(source: str, name: str, body: str) -> str:
    matches = list(re.finditer(r"\b(?:public|private) " + re.escape(name) + r"\([^\n]*\)[^\n{]*\{", source))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one script function: {name}")
    start = matches[0].end()
    depth, quote, escaped = 1, False, False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if not depth:
                return source[:start] + "\n" + body + "\n" + source[index:]
    raise ValueError(f"Unterminated script function: {name}")


def validate_function_contracts(source: str, canonical: str) -> None:
    pattern = r"^(public|private) ([^\s(]+)\("
    original = set(re.findall(pattern, source, re.MULTILINE))
    rebuilt = set(re.findall(pattern, canonical, re.MULTILINE))
    if original != rebuilt:
        raise ValueError(f"Script compilation changed named function contracts: missing {sorted(original - rebuilt)}, added {sorted(rebuilt - original)}")


def validate_runtime_calls(source: str, canonical: str) -> None:
    """Reject compiler round trips that silently drop injected helper calls."""
    pattern = r"\b(rando_[A-Za-z0-9_]+)\*?\s*\("
    def calls(text: str) -> Counter[str]:
        code = "".join(re.split(r'("(?:[^"\\]|\\.)*"|//[^\n]*)', text)[::2])
        return Counter(re.findall(pattern, code))
    original = calls(source)
    rebuilt = calls(canonical)
    if original != rebuilt:
        raise ValueError(f"Script compilation changed randomizer calls: missing {dict(original - rebuilt)}, added {dict(rebuilt - original)}")


def lower_temporary_registers(source: str) -> str:
    """Use real locals for injected scratch registers outside native temp 0–19.

    The native resolver indexes a fixed bank at Runtime+0x198. Compiler support
    for an eight-bit encoded ID does not make tempVar90 a valid native register.
    Preserve quoted strings and original registers and allocate within each
    function's separate local namespace.
    """
    pattern = re.compile(r"^(?:public|private) [^\s(]+\(([^\n]*)\)[^\n{]*\{", re.MULTILINE)
    edits: list[tuple[int, int, str]] = []
    for match in pattern.finditer(source):
        if any(int(value) >= 20 for value in re.findall(r"\btempVar([0-9]+)\b", match.group(1))):
            raise ValueError("Native function arguments must use temporary registers 0–19")
        start = match.end()
        depth, quoted, escaped = 1, False, False
        end = start
        for end in range(start, len(source)):
            character = source[end]
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    break
        if depth:
            raise ValueError("Unterminated native script function")
        parts = re.split(r'("(?:[^"\\]|\\.)*")', source[start:end])
        code = "".join(parts[::2])
        high = sorted({int(value) for value in re.findall(r"\btempVar([0-9]+)\b", code) if int(value) >= 20})
        if not high:
            continue
        used = {int(value) for value in re.findall(r"\blocalVar([0-9]+)\b", code + match.group(1))}
        for value in re.findall(r"\bvar_0x([0-9a-fA-F]+)\b", code):
            identifier = int(value, 16)
            if identifier & 0xFFFF00FF == 0x20000000:
                used.add((identifier >> 8) & 255)
        # Original named arrays generally occupy the low local IDs. Allocate
        # high free IDs while also preserving explicitly encoded local aliases.
        available = [index for index in reversed(range(256)) if index not in used]
        if len(available) < len(high):
            raise ValueError("Injected scratch values exceed native local-variable capacity")
        mapping = dict(zip(high, available, strict=False))
        for index in range(0, len(parts), 2):
            part = parts[index]
            for temporary, local in mapping.items():
                part = re.sub(r"\btemp(?=\s+tempVar" + str(temporary) + r"\b)", "local", part)
                part = re.sub(r"\btempVar" + str(temporary) + r"\b", f"localVar{local}", part)
            parts[index] = part
        edits.append((start, end, "".join(parts)))
    for start, end, body in reversed(edits):
        source = source[:start] + body + source[end:]
    return source


@dataclass(frozen=True)
class ScriptSource:
    binary: Path
    source: Path
    header: Path
    original_sha256: str


def decompile(project: RomProject, filename: str, work: Path, compiler: Path) -> ScriptSource:
    binary = work / filename
    binary.parent.mkdir(parents=True, exist_ok=True)
    original = project.read_file(filename)
    binary.write_bytes(original)
    compile_script(compiler, binary)
    return ScriptSource(binary, binary.with_suffix(".cksm"), binary.with_suffix(".hksm"), hashlib.sha256(original).hexdigest())


def add_declarations(header: str, flags: tuple[str, ...], native_imports: dict[str, str]) -> str:
    for name, declaration in native_imports.items():
        if not re.search(r"#import (?:function|int) " + re.escape(name) + r"\b", header):
            header += "\n" + declaration
    for flag in flags:
        if not re.search(r"static user " + re.escape(flag) + r";", header):
            header += f"\nstatic user {flag};"
    return header + "\n"


def compile_checked(script: ScriptSource, compiler: Path, flags: tuple[str, ...], required_function: str | None = "rando_deliver") -> bytes:
    source = lower_temporary_registers(script.source.read_text(encoding="utf-8"))
    script.source.write_text(source, encoding="utf-8")
    compile_script(compiler, script.source)
    rebuilt = script.binary.with_suffix(".re.bin")
    result = rebuilt.read_bytes()
    parsed = KsmDocument(result)
    names = {variable.name for variable in parsed.statics if variable.type == KsmValueType.SAVE_VARIABLE}
    if set(flags) - names:
        raise ValueError(f"Compiled delivery script lost save-variable references: {sorted(set(flags) - names)}")
    compile_script(compiler, rebuilt)
    canonical = rebuilt.with_suffix(".cksm").read_text(encoding="utf-8")
    validate_function_contracts(source, canonical)
    validate_runtime_calls(source, canonical)
    if required_function is not None and required_function not in canonical:
        raise ValueError(f"Compiled script {script.binary.name} lost required function {required_function}")
    return result

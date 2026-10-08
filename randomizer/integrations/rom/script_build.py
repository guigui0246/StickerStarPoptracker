"""Checked script transformations using the external Gibberish compiler."""

from dataclasses import dataclass
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
    source = script.source.read_text(encoding="utf-8")
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
    if required_function is not None and required_function not in canonical:
        raise ValueError("Compiled delivery script lost its delivery function")
    return result

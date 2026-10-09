"""Package LayeredFS files under the exact emulator title directory."""

from pathlib import Path
import tempfile
import zipfile

from .native_recipe import NativeRecipe, apply_native_recipe
from .project import RomProject
from .seed_patch import TITLE_ID


def build_mod_archive(project: RomProject, recipe: NativeRecipe, output: Path, compiler: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise FileExistsError("Existing archives are preserved; choose a new output path")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mod-archive-", dir=output.parent) as directory:
        work = Path(directory)
        mod = apply_native_recipe(project, recipe, work / "mod", compiler)
        archive = work / "mod.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
            for path in sorted(mod.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(mod)
                # Reports and source assembly stay outside the installation tree.
                if relative.parts[0] in {"romfs", "exefs"} and path.suffix != ".S":
                    destination = f"{TITLE_ID}/{relative.as_posix()}"
                else:
                    destination = "reports/" + relative.as_posix()
                stream.write(path, destination)
        archive.rename(output)
    return output

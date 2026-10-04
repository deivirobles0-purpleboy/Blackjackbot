"""Build a Square Cloud archive from an explicit list; never bundle local secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = ("bot.py", "requirements.txt", "squarecloud.app", "README.md", "VALIDATION.md", ".env.example")
DIRECTORIES = ("config", "database", "cogs", "halloween", "utils")


def build() -> Path:
    target = ROOT / "halloween-squarecloud.zip"
    sources = [ROOT / name for name in FILES]
    sources += [path for name in DIRECTORIES for path in (ROOT / name).glob("*.py")]
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(sources):
            archive.write(path, path.relative_to(ROOT).as_posix())
    return target


if __name__ == "__main__":
    print(build())

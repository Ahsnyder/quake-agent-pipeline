"""Create a source-and-deliverables ZIP without environments, caches or secrets."""

import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = [".gitignore", ".gitattributes", ".env.example", "LICENSE", "README.md", "pyproject.toml", "requirements.lock"]
DIRECTORIES = [".github", "quake_pipeline", "tests", "scripts", "docs", "examples/demo", "output/pdf"]
SECRET_PATTERN = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}|AIza[0-9A-Za-z_-]{35}")


def main():
    files = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        files.extend(p for p in (ROOT / name).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    files = sorted(set(files))
    for path in files:
        if SECRET_PATTERN.search(path.read_bytes()):
            raise ValueError(f"Possible credential detected in {path.relative_to(ROOT)}; packaging stopped")
    output = ROOT.parent / "quake-agent-pipeline.zip"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=Path(ROOT.name) / path.relative_to(ROOT))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        print(f"Packaged {len(archive.namelist())} files: {output}")


if __name__ == "__main__":
    main()

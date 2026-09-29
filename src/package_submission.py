"""Create an offline submission ZIP from an explicit artifact allowlist."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from query import DEFAULT_FACTS, ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/sbb-framex-submission.zip")
    args = parser.parse_args(argv)
    files = [ROOT / name for name in ("README.md", "AGENTS.md", "ontology.fx", "pyproject.toml",
                                     "uv.lock", ".python-version", ".gitignore")]
    files += DEFAULT_FACTS
    for folder in ("src", "tests", "docs"):
        files.extend(p for p in (ROOT / folder).rglob("*") if p.is_file()
                     and "__pycache__" not in p.parts and p.suffix in {".py", ".md", ".json", ".fx"})
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        parser.error("Prepare missing artifacts first: " + ", ".join(missing))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        count = len(archive.namelist())
    print(f"Created {args.output}: {count} files, {args.output.stat().st_size:,} bytes; integrity checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

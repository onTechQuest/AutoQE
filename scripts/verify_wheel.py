"""Validate AutoQE's distribution boundary without importing or extracting it."""

import argparse
from pathlib import Path, PurePosixPath
import tomllib
from zipfile import ZipFile


def verify_wheel(wheel: Path, root: Path) -> dict[str, int]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    metadata_root = f"autoqe-{config['project']['version']}.dist-info"
    packages = {"autoqe": root / "src/autoqe", "autoqe_integration": root / "autoqe_integration"}
    expected = {
        f"{name}/{path.relative_to(source).as_posix()}": path.read_bytes().replace(b"\r\n", b"\n")
        for name, source in packages.items() for path in source.rglob("*.py")
    }
    counts = dict.fromkeys([*packages, metadata_root], 0)
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate wheel members")
        for name in names:
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name
                    or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}
                    or not path.parts or path.parts[0] not in counts):
                raise ValueError(f"Forbidden wheel member: {name}")
            counts[path.parts[0]] += 1
            if path.parts[0] in packages:
                if name not in expected:
                    raise ValueError(f"Unexpected package file: {name}")
                if archive.read(name).replace(b"\r\n", b"\n") != expected[name]:
                    raise ValueError(f"Package source mismatch: {name}")
        missing = set(expected) - set(names)
        missing |= {f"{metadata_root}/{name}" for name in ("METADATA", "WHEEL", "RECORD")} - set(names)
        if missing or any(count == 0 for count in counts.values()):
            raise ValueError(f"Incomplete wheel: {sorted(missing)}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel_directory", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.wheel_directory.glob("*.whl"))
    if len(wheels) != 1:
        parser.error("Expected exactly one wheel; use a fresh output directory")
    try:
        counts = verify_wheel(wheels[0], Path(__file__).resolve().parents[1])
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Wheel validation failed: {exc}\n")
    print(f"Wheel boundary PASS: {counts}")


if __name__ == "__main__":
    main()

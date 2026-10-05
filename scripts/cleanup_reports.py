"""Explicit, dry-run-first housekeeping restricted to this checkout's reports/."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import stat
import time


ROOT = Path(__file__).resolve().parents[1]
PROTECTED = {".git", ".venv", "venv", "env", "src", "examples", "docs", "qualification",
             "autoqe", "autoqe_integration"}


@dataclass(frozen=True)
class Entry:
    path: Path
    directory: bool
    size: int
    identity: tuple[int, int, int, int]


def _checked(path: Path, reports: Path):
    """Check every ancestor without trusting resolve() alone to detect links."""
    relative = path.relative_to(reports)
    if ".." in relative.parts or any(part.lower() in PROTECTED for part in relative.parts):
        raise ValueError("Protected or traversal path in reports")
    for item in (reports, *[reports.joinpath(*relative.parts[:i]) for i in range(1, len(relative.parts) + 1)]):
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Links and reparse points are not cleanup targets")
    if not path.resolve(strict=True).is_relative_to(reports):
        raise ValueError("Cleanup target escaped reports")
    return info


def plan_cleanup(root: Path, older_than_days: int | None = None, *, now: float | None = None) -> list[Entry]:
    root = root.resolve(strict=True)
    reports = root / "reports"
    if older_than_days is not None and older_than_days < 0:
        raise ValueError("Age must be nonnegative")
    # lstat also detects dangling Windows junctions without following them.
    try:
        reports.lstat()
    except FileNotFoundError:
        return []
    info = _checked(reports, reports)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("reports must be a directory")
    cutoff = (time.time() if now is None else now) - older_than_days * 86400 if older_than_days is not None else None
    entries = []

    def visit(path):
        info = _checked(path, reports)
        directory = stat.S_ISDIR(info.st_mode)
        if not directory and not stat.S_ISREG(info.st_mode):
            raise ValueError("Unsupported file type in reports")
        eligible = cutoff is None or info.st_mtime <= cutoff
        if directory:
            # Visit all children even when one is retained: validate the whole tree.
            children = [visit(child) for child in sorted(path.iterdir())]
            eligible = eligible and all(children)
        if eligible:
            entries.append(Entry(path, directory, 0 if directory else info.st_size,
                                 (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)))
        return eligible

    for child in sorted(reports.iterdir()):
        visit(child)
    return entries


def cleanup(root: Path, older_than_days: int | None = None, *, confirm: bool = False) -> list[Entry]:
    root = root.resolve(strict=True)
    reports = root / "reports"
    entries = plan_cleanup(root, older_than_days)
    if confirm:
        # Validate the entire plan again before the first deletion.
        for entry in entries:
            info = _checked(entry.path, reports)
            if (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size) != entry.identity:
                raise ValueError("Reports changed after planning; retry with writers stopped")
        for entry in entries:
            info = _checked(entry.path, reports)
            if (info.st_dev, info.st_ino) != entry.identity[:2]:
                raise ValueError("Cleanup target changed")
            if entry.directory:
                entry.path.rmdir()  # Empty only; never recursively follows a target.
            else:
                if (info.st_mtime_ns, info.st_size) != entry.identity[2:]:
                    raise ValueError("Report changed after planning")
                entry.path.unlink()
    return entries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--older-than-days", type=int)
    selection.add_argument("--all", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    if args.older_than_days is not None and args.older_than_days < 0:
        parser.error("--older-than-days must be nonnegative")
    if args.confirm and not args.all and args.older_than_days is None:
        parser.error("--confirm requires --all or --older-than-days")
    try:
        entries = cleanup(ROOT, args.older_than_days, confirm=args.confirm)
    except (OSError, ValueError):
        print("Cleanup refused: unsafe, protected, inaccessible or changed reports tree; no further deletion.")
        return 2
    action = "DELETED" if args.confirm else "DRY RUN: would delete"
    for entry in entries:
        print(f"{action} {'directory' if entry.directory else 'file'} reports/{entry.path.relative_to(ROOT / 'reports').as_posix()}")
    print(f"{action}: {sum(not e.directory for e in entries)} files, "
          f"{sum(e.directory for e in entries)} directories, {sum(e.size for e in entries)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

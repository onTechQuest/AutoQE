import argparse
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qualification.m4.harness import qualify


def main() -> int:
    parser = argparse.ArgumentParser(description="External local M4 qualification controller (Windows).")
    parser.add_argument("--rwa-root", type=Path, default=Path("C:/Projects/autoqe-reference-rwa"))
    parser.add_argument("--yarn-js", type=Path, default=Path.home() / "AppData/Roaming/npm/node_modules/yarn/bin/yarn.js")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / uuid4().hex)
    args = parser.parse_args()
    return 0 if qualify(args.rwa_root, args.yarn_js, args.output)["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

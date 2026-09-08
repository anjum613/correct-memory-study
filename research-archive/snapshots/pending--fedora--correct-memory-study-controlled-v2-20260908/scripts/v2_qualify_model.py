#!/usr/bin/env python3
"""Prepare exact-model V2 qualification evidence without study-family input."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cmpilot.v2_qualification import cpu_preflight


ROOT = Path(__file__).parents[1]
PROFILES = {
    "qwen": ROOT / "configs/v2/models/qwen2.5-coder-32b-instruct.json",
    "devstral": ROOT / "configs/v2/models/devstral-small-2507.json",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=tuple(PROFILES), required=True)
    parser.add_argument(
        "--artifact-root", type=Path, default=ROOT / "artifacts/v2-preflight"
    )
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    record = cpu_preflight(PROFILES[args.model], args.artifact_root)
    output = args.artifact_root / f"qualification-{args.model}.json"
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"model": args.model, "output": str(output), "status": record["overall_status"]}))
    return 0 if record["overall_status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())

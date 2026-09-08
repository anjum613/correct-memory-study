#!/usr/bin/env python3
"""Write final V2 methodology-repair readiness artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from cmpilot.v2_methodology_readiness import build


ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "artifacts/v2-methodology-repair"


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    readiness, classifications, prompts = build(ROOT)
    _write(OUTPUT / "readiness.json", readiness)
    _write(OUTPUT / "test-classification.json", classifications)
    _write(OUTPUT / "prompt-census-validation.json", prompts)
    print(
        json.dumps(
            {
                "non_gpu_study_readiness": readiness["non_gpu_study_readiness"],
                "v2_fixtures_ready": sum(readiness["v2_fixture_ready_by_family"].values()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

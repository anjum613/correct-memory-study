#!/usr/bin/env python3
"""Create the immutable record for the pinned staged Devstral snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import MODEL_ID, MODEL_REVISION, MODEL_SNAPSHOT  # noqa: E402
from cmpilot.devstral_snapshot_freeze import (  # noqa: E402
    PINNED_DEVSTRAL_SNAPSHOT,
    SNAPSHOT_FREEZE,
    create_devstral_snapshot_freeze,
    write_devstral_snapshot_freeze_atomic,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=MODEL_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=ROOT / SNAPSHOT_FREEZE)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--revision", default=MODEL_REVISION)
    arguments = parser.parse_args()

    if arguments.model_id != PINNED_DEVSTRAL_SNAPSHOT.model_id:
        raise ValueError("model ID does not match the pinned Devstral identity")
    if arguments.revision != PINNED_DEVSTRAL_SNAPSHOT.revision:
        raise ValueError("revision does not match the pinned Devstral identity")
    record = create_devstral_snapshot_freeze(arguments.snapshot)
    freeze_sha256 = write_devstral_snapshot_freeze_atomic(arguments.output, record)
    print(
        json.dumps(
            {
                "freeze": str(arguments.output),
                "freeze_sha256": freeze_sha256,
                "model_id": arguments.model_id,
                "revision": arguments.revision,
                "snapshot_identity_sha256": record["snapshot"]["identity_sha256"],
                "status": "FROZEN",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

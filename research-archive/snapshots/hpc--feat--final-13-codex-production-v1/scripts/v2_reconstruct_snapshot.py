#!/usr/bin/env python3
"""Reconstruct one V2 snapshot from committed/content-addressed inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cmpilot.v2_snapshot_overlay import reconstruct_snapshot


ROOT = Path(__file__).parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=("axios-v1", "aim-v1", "httpx-v1"))
    parser.add_argument("state", choices=("source", "compatible", "invalidated"))
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = reconstruct_snapshot(
        repository_root=ROOT,
        manifest_path=ROOT / "v2/fixtures/snapshot-overlays/manifest.json",
        family=args.family,
        state=args.state,
        destination=args.destination,
    )
    print(
        json.dumps(
            {
                "family": result.family,
                "state": result.state,
                "repository_sha256": result.repository_sha256,
                "overlay_file_count": result.overlay_file_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

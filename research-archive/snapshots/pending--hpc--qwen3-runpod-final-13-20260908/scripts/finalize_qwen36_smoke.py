#!/usr/bin/env python3
"""Create the self-excluding artifact manifest for one Qwen3.6 smoke job."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import (  # noqa: E402
    sha256_file,
    write_canonical_json,
)


EXCLUDED = frozenset({"artifact-manifest.json", "artifact-manifest.sha256"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_directory", type=Path)
    arguments = parser.parse_args()
    artifact = arguments.artifact_directory.resolve(strict=True)
    rows = []
    errors = []
    for path in sorted(artifact.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact).as_posix()
        if relative in EXCLUDED:
            continue
        try:
            rows.append(
                {
                    "bytes": path.stat().st_size,
                    "path": relative,
                    "sha256": sha256_file(path),
                }
            )
        except OSError as error:
            errors.append(f"{relative}: {type(error).__name__}: {error}")
    manifest = {
        "algorithm": "sha256 exact file bytes",
        "entry_count": len(rows),
        "errors": errors,
        "files": rows,
        "pass": not errors,
        "schema": "qwen36-serving-smoke-artifact-manifest-v1",
        "self_excluding": True,
    }
    manifest_path = artifact / "artifact-manifest.json"
    write_canonical_json(manifest_path, manifest, exclusive=True)
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    (artifact / "artifact-manifest.sha256").write_text(
        digest + "\n", encoding="ascii", newline="\n"
    )
    print(json.dumps({"manifest_sha256": digest, **manifest}, sort_keys=True))
    return 0 if manifest["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

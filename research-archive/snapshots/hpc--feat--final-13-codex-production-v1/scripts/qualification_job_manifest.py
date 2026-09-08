#!/usr/bin/env python3
"""Create and validate a self-excluding manifest for one qualification job."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXCLUDED = {"SHA256SUMS", "job-manifest.json"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    arguments = parser.parse_args()
    artifact = arguments.artifact.resolve(strict=True)
    rows = []
    for path in sorted(artifact.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact).as_posix()
        if relative in EXCLUDED:
            continue
        rows.append((digest(path), relative))
    text = "".join(f"{value}  {relative}\n" for value, relative in rows)
    (artifact / "SHA256SUMS").write_text(text, encoding="ascii", newline="\n")
    regenerated = "".join(
        f"{digest(artifact / relative)}  {relative}\n" for _, relative in rows
    )
    record = {
        "algorithm": "sha256 exact file bytes",
        "entry_count": len(rows),
        "errors": [],
        "manifest_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "pass": regenerated == text,
        "schema": "qwen32b-qualification-job-manifest-v1",
        "self_excluding": True,
    }
    (artifact / "job-manifest.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, sort_keys=True))
    return 0 if record["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

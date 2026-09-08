#!/usr/bin/env python3
"""Freeze exact ignored V1 bytes as deterministic, V2-only overlays."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
from typing import Any

from cmpilot.repository_manager import repository_content_digest
from cmpilot.v2_snapshot_overlay import OVERLAY_SCHEMA


ROOT = Path(__file__).parents[1]
DEFAULT_OUTPUT = ROOT / "v2/fixtures/snapshot-overlays"
HISTORICAL_ROOTS = {
    "axios-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-mcp-pinot-v01/families/axios-v1"
    ),
    "aim-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-aim-v01/families/aim-v1"
    ),
    "httpx-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-httpx-v01/families/httpx-v1"
    ),
}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _all_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _missing_files(clean: Path, historical: Path) -> list[tuple[str, Path]]:
    clean_files = _all_files(clean)
    historical_files = _all_files(historical)
    for relative in sorted(set(clean_files) & set(historical_files)):
        if clean_files[relative].read_bytes() != historical_files[relative].read_bytes():
            raise RuntimeError(f"historical file differs from Git-visible file: {relative}")
    missing = sorted(set(historical_files) - set(clean_files))
    if not missing:
        raise RuntimeError(f"no missing files found beneath {historical}")
    return [(relative, historical_files[relative]) for relative in missing]


def _archive(rows: list[dict[str, Any]], payloads: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for row in rows:
                name = str(row["archive_path"])
                payload = payloads[name]
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                info.mode = int(str(row["mode"]), 8)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                tar.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def build(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    families: dict[str, Any] = {}
    for family, historical_family in HISTORICAL_ROOTS.items():
        clean_family = ROOT / "families" / family
        package = json.loads((clean_family / "family-package.json").read_text())
        state_keys = {
            "source": "source_repository",
            "compatible": "compatible_repository",
            "invalidated": "target_repository",
        }
        rows: list[dict[str, Any]] = []
        payloads: dict[str, bytes] = {}
        states: dict[str, Any] = {}
        for state, package_key in state_keys.items():
            clean = clean_family / "repositories" / state
            historical = historical_family / "repositories" / state
            clean_digest = repository_content_digest(clean).sha256
            historical_digest = repository_content_digest(historical).sha256
            expected = package["inputs"][package_key]["sha256"]
            if historical_digest != expected:
                raise RuntimeError(f"historical digest mismatch: {family}/{state}")
            missing = _missing_files(clean, historical)
            for relative, path in missing:
                payload = path.read_bytes()
                archive_path = f"{state}/{relative}"
                mode = "0755" if stat.S_IMODE(path.stat().st_mode) & 0o111 else "0644"
                row = {
                    "archive_path": archive_path,
                    "bytes": len(payload),
                    "mode": mode,
                    "relative_path": relative,
                    "sha256": _sha256_bytes(payload),
                    "state": state,
                }
                rows.append(row)
                payloads[archive_path] = payload
            states[state] = {
                "git_visible_repository_sha256": clean_digest,
                "reconstructed_repository_sha256": historical_digest,
                "overlay_file_count": len(missing),
            }
        rows.sort(key=lambda row: str(row["archive_path"]).encode("utf-8"))
        archive_payload = _archive(rows, payloads)
        archive_sha256 = _sha256_bytes(archive_payload)
        archive_name = f"sha256-{archive_sha256}.tar.gz"
        (output / archive_name).write_bytes(archive_payload)
        families[family] = {
            "archive": archive_name,
            "archive_bytes": len(archive_payload),
            "archive_sha256": archive_sha256,
            "files": rows,
            "historical_source": str(historical_family),
            "states": states,
        }
    manifest = {
        "schema": OVERLAY_SCHEMA,
        "construction": (
            "Exact regular files present in the preserved V1 historical family tree "
            "and absent from the Git-visible audit-HEAD tree; no existing byte differs."
        ),
        "families": families,
        "v1_files_modified": False,
    }
    (output / "manifest.json").write_bytes(_canonical(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(args.output)
    print(
        json.dumps(
            {
                family: sum(state["overlay_file_count"] for state in row["states"].values())
                for family, row in result["families"].items()
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

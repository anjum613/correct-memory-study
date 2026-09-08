#!/usr/bin/env python3
"""Stage and validate exactly one immutable Qwen3.6-27B Hub snapshot."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import (  # noqa: E402
    ARTIFACT_ROOT,
    MODEL_CACHE,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    QUALIFICATION_NAMESPACE,
    filtered_remote_metadata,
    memory_feasibility,
    validate_remote_metadata,
    validate_snapshot,
    write_canonical_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=MODEL_CACHE)
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=ROOT / QUALIFICATION_NAMESPACE / "model-metadata.json",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=ROOT / QUALIFICATION_NAMESPACE / "model-staging-manifest.json",
    )
    parser.add_argument(
        "--artifact-directory",
        type=Path,
        default=ARTIFACT_ROOT / "model-staging",
    )
    arguments = parser.parse_args()
    for path in (
        arguments.metadata_output,
        arguments.manifest_output,
        arguments.artifact_directory,
    ):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"staging output already exists: {path}")

    from huggingface_hub import HfApi, snapshot_download

    started = datetime.now(UTC).isoformat()
    api = HfApi()
    info = api.model_info(MODEL_ID, revision=MODEL_REVISION, files_metadata=True)
    metadata = filtered_remote_metadata(info)
    validate_remote_metadata(metadata)
    if info.sha != MODEL_REVISION:
        raise RuntimeError("Hub resolved the pin to a different revision")

    cache_root = arguments.cache_root.resolve()
    expected_snapshot = (
        cache_root
        / "hub/models--Qwen--Qwen3.6-27B/snapshots"
        / MODEL_REVISION
    )
    os.environ["HF_HOME"] = str(cache_root)
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    downloaded = Path(
        snapshot_download(
            repo_id=MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=cache_root / "hub",
            local_files_only=False,
        )
    ).resolve(strict=True)
    if downloaded != expected_snapshot.resolve(strict=True):
        raise RuntimeError(
            f"Hub snapshot path mismatch: {downloaded} != {expected_snapshot}"
        )
    if expected_snapshot != MODEL_SNAPSHOT:
        raise RuntimeError("cache root differs from the approved model cache")

    validation = validate_snapshot(downloaded, metadata, hash_weights=True)
    manifest = {
        "completed_at_utc": datetime.now(UTC).isoformat(),
        "download_revision_argument": MODEL_REVISION,
        "memory_feasibility": memory_feasibility(),
        "model": validation,
        "network_required_after_staging": False,
        "schema": "qwen36-model-staging-manifest-v1",
        "staged_only_pinned_revision": True,
        "started_at_utc": started,
    }
    arguments.artifact_directory.mkdir(parents=True, mode=0o700)
    write_canonical_json(arguments.artifact_directory / "model-metadata.json", metadata)
    write_canonical_json(arguments.artifact_directory / "model-staging-manifest.json", manifest)
    write_canonical_json(arguments.metadata_output, metadata, exclusive=True)
    write_canonical_json(arguments.manifest_output, manifest, exclusive=True)
    print(
        json.dumps(
            {
                "manifest": str(arguments.manifest_output),
                "model_id": MODEL_ID,
                "revision": MODEL_REVISION,
                "snapshot": str(downloaded),
                "status": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

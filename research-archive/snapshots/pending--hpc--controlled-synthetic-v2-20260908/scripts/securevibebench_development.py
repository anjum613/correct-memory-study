#!/usr/bin/env python3
"""Create pinned, metadata-only SecureVibeBench development manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from cmpilot.securevibebench_development import (
    SEEN_IDS,
    canonical_json,
    collapse_duplicates,
    deterministic_order,
    guard_instance_access,
    load_seen_ids,
    normalize_crash_fingerprint,
    normalized_metadata_hash,
    sha256_bytes,
)


ORDER_SALT = "correct-memory-securevibebench-v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    import subprocess

    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def extract_crash_state(meta: dict[str, Any]) -> list[str]:
    for comment in meta.get("report", {}).get("comments", []):
        content = str(comment.get("content", ""))
        marker = "Crash State:"
        if marker not in content:
            continue
        tail = content.split(marker, 1)[1]
        frames = []
        for line in tail.splitlines()[1:]:
            line = line.strip()
            if not line:
                break
            frames.append(line)
        return frames[:3]
    return []


def load_arvo_metadata(meta_dir: Path, localid: str) -> dict[str, Any]:
    path = meta_dir / f"{localid}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    frames = extract_crash_state(data)
    return {
        "localid": localid,
        "vfc": str(data.get("fix_commit") or str(data.get("fix", "")).rstrip("/").split("/")[-1]),
        "project": str(data.get("project", "")),
        "sanitizer": str(data.get("sanitizer", "")),
        "crash_type": str(data.get("crash_type", "")),
        "crash_state": frames,
        "fingerprint": normalize_crash_fingerprint(str(data.get("crash_type", "")), frames),
        "metadata_sha256": file_sha256(path),
    }


def docker_tag_record(localid: str, mode: str) -> dict[str, Any]:
    tag = f"{localid}-{mode}"
    url = f"https://hub.docker.com/v2/repositories/n132/arvo/tags/{tag}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = json.load(response)
    amd64 = next(image for image in data.get("images", []) if image.get("architecture") == "amd64" and image.get("os") == "linux")
    return {
        "name": f"n132/arvo:{tag}",
        "digest": amd64["digest"],
        "compressed_size_bytes": amd64["size"],
        "architecture": "amd64",
        "os": "linux",
        "last_pushed": amd64.get("last_pushed"),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n")


def build(args: argparse.Namespace) -> None:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit("pyarrow==21.0.0 is required for pinned Parquet input") from exc

    seen = load_seen_ids(args.seen_set)
    table = pq.read_table(args.dataset_parquet)
    rows = table.to_pylist()
    ids = [str(row["localid"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate raw localid in dataset")
    if not set(seen).issubset(ids):
        raise ValueError("seen development ID missing from pinned dataset")

    unseen = sorted(set(ids) - set(seen), key=int)
    for localid in unseen:
        guard_instance_access(localid, seen, fields=["localid"])

    output = args.output
    dataset_revision = git_head(args.dataset_repo)
    images = [docker_tag_record(localid, mode) for localid in seen for mode in ("vul", "fix")]
    arvo_seen = [load_arvo_metadata(args.arvo_meta / "archive_data/meta", localid) for localid in seen]
    seen_rows = [row for row in rows if str(row["localid"]) in set(seen)]

    source_lock = {
        "schema": "securevibebench-source-lock-v1",
        "securevibebench_repository": "https://github.com/iCSawyer/SecureVibeBench",
        "securevibebench_commit": git_head(args.securevibebench),
        "securevibebench_dataset": "https://huggingface.co/datasets/iCSawyer/SecureVibeBench",
        "securevibebench_dataset_revision": dataset_revision,
        "dataset_parquet_path": "data/train-00000-of-00001.parquet",
        "dataset_parquet_sha256": file_sha256(args.dataset_parquet),
        "dataset_parquet_size_bytes": args.dataset_parquet.stat().st_size,
        "normalized_task_metadata_sha256": normalized_metadata_hash(rows),
        "normalized_seen_task_metadata_sha256": normalized_metadata_hash(seen_rows),
        "arvo_repository": "https://github.com/n132/ARVO",
        "arvo_commit": git_head(args.arvo),
        "arvo_meta_repository": "https://github.com/n132/ARVO-Meta",
        "arvo_meta_commit": git_head(args.arvo_meta),
        "docker_images": images,
        "dependency_versions": {"pyarrow": "21.0.0"},
        "floating_references_permitted": False,
    }
    write_json(output / "source-lock.json", source_lock)

    seen_bytes = args.seen_set.read_bytes()
    write_json(
        output / "seen-set-manifest.json",
        {
            "schema": "securevibebench-seen-set-manifest-v1",
            "seen_ids": list(seen),
            "declaration_path": str(args.seen_set.resolve().relative_to(args.repository_root.resolve())),
            "declaration_sha256": sha256_bytes(seen_bytes),
            "declared_before_candidate_development_commit": git_head(args.repository_root),
            "future_confirmatory_exclusion": True,
            "dataset_revision": dataset_revision,
        },
    )
    write_json(
        output / "unseen-universe.json",
        {
            "schema": "securevibebench-unseen-universe-v1",
            "dataset_revision": dataset_revision,
            "raw_task_count": len(ids),
            "seen_ids": list(seen),
            "unseen_task_count": len(unseen),
            "unseen_ids": unseen,
            "contents": "identifiers_only",
            "implementation_details_inspected": False,
        },
    )

    # Read only metadata columns from Parquet for unseen dedupe construction.
    basic = pq.read_table(args.dataset_parquet, columns=["localid", "repo_url", "vic"]).to_pylist()
    by_id = {str(row["localid"]): row for row in basic}
    all_dedupe_rows = []
    missing_meta = []
    for localid in ids:
        try:
            arvo = load_arvo_metadata(args.arvo_meta / "archive_data/meta", localid)
        except FileNotFoundError:
            missing_meta.append(localid)
            continue
        guard_instance_access(localid, seen, fields=["localid", "repo_url", "vic", "vfc", "project", "sanitizer", "crash_type", "crash_state"])
        all_dedupe_rows.append({**by_id[localid], **arvo})
    groups = collapse_duplicates(all_dedupe_rows)
    seen_groups = [group for group in groups if set(group["member_ids"]) & set(seen)]
    unseen_groups = [group for group in groups if set(group["member_ids"]).issubset(set(unseen))]
    write_json(
        output / "deduplication-test.json",
        {
            "schema": "securevibebench-metadata-deduplication-v1",
            "key_fields": ["normalized_repository", "vic", "vfc"],
            "fingerprint_role": "diagnostic; cannot split identical repository/VIC/VFC transformations",
            "seen_groups": seen_groups,
            "seen_raw_count": len(seen),
            "seen_deduplicated_count": len(seen_groups),
            "unseen_raw_count": len(unseen),
            "deduplicated_unseen_count": len(unseen_groups),
            "missing_arvo_metadata_ids": sorted(missing_meta, key=int),
        },
    )
    write_json(
        output / "future-order-preview.json",
        {
            "schema": "securevibebench-future-order-unexecuted-v1",
            "salt": ORDER_SALT,
            "rule": "ascending SHA256(salt + '|' + canonical_instance_id), integer ID tie-break",
            "canonical_ids": deterministic_order((group["canonical_instance_id"] for group in unseen_groups), ORDER_SALT),
            "semantic_screening_executed": False,
        },
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repository-root", type=Path, required=True)
    result.add_argument("--seen-set", type=Path, required=True)
    result.add_argument("--dataset-parquet", type=Path, required=True)
    result.add_argument("--dataset-repo", type=Path, required=True)
    result.add_argument("--securevibebench", type=Path, required=True)
    result.add_argument("--arvo", type=Path, required=True)
    result.add_argument("--arvo-meta", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    return result


if __name__ == "__main__":
    build(parser().parse_args())

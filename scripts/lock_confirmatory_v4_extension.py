#!/usr/bin/env python3
"""Prepare target-scoped artifacts and lock one frozen V4 extension target."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from cmpilot.content_audit_v4 import ContentAccessAudit, TreeRef
from cmpilot.development_validation_v3 import render_yaml
from cmpilot.production_v4 import PublicTargetBundle, lock_top_source_v4
from cmpilot.source_pairing import (
    SourcePairingError,
    classify_task_statement,
    stable_record_hash,
)
from cmpilot.susvibes_feasibility import SUSVIBES_REVISION, tree_sha256
from cmpilot.target_identity_v3 import TargetIdentityScope


EXTENSION_IDS = (
    "vyperlang__vyper_851f7a1b3aa2a36fd041e3d0ed38f9355a58c8ae",
    "openstack__aodh_149d3ad2193b4d17df801f82a0a6be62dba564db",
    "urllib3__urllib3_a74c9cfbaed9f811e7563cfc3dce894928e0221a",
    "tensorflow__tensorflow_dbdd98c37bc25249e8f288bd30d01e118a7b4498",
    "django__django_1f2dd37f6fcefdd10ed44cb233b2e62b520afb38",
)
TARGETS = {
    EXTENSION_IDS[0]: {
        "image": "songwen6968/susvibes.x86_64.eval_vyperlang_vyper_851f7a1b3aa2a36fd041e3d0ed38f9355a58c8ae",
        "manifest_digest": "sha256:f9e7219d2912d2835ba3fc7ea69b3ece4182438941b0c662a0d856e6a7ec6f71",
        "environment_artifact_relative": f"images/{EXTENSION_IDS[0]}.sif",
        "environment_artifact_sha256": "94580d56bbe3ae13d05ef30413bac66b5c60af195d5c9b13d2c91979cc551f67",
        "project": "vyperlang/vyper",
        "target_b_date_utc": "2023-04-24",
        "timestamp_source": "https://api.github.com/repos/vyperlang/vyper/commits/851f7a1b3aa2a36fd041e3d0ed38f9355a58c8ae",
    },
    EXTENSION_IDS[1]: {
        "image": "songwen6968/susvibes.x86_64.eval_openstack_aodh_149d3ad2193b4d17df801f82a0a6be62dba564db",
        "manifest_digest": "sha256:e1054afad43031257d341bf1b1a6a1c5720d255deb00a79ac8925e4ca8bb10fd",
        "environment_artifact_relative": f"cases/{EXTENSION_IDS[1]}/environment.provenance",
        "environment_artifact_sha256": "901ea915cf2cf29ba3d5a9f6c2bf437bfe41ab520279c757a4003a21d0bf0caf",
        "project": "openstack/aodh",
        "target_b_date_utc": "2018-04-24",
        "timestamp_source": "FROZEN_SUSVIBES_ROW:cve_fix_date",
    },
}
EXCLUSION_PROTOCOL_SHA256 = (
    "60f48bfa520232d70808df97280a7142c6ec56df083ae37babfdd856a1ef0854"
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _one_dataset_row(payload: bytes, target_id: str) -> tuple[bytes, dict[str, Any]]:
    prefix = b'{"instance_id": ' + json.dumps(target_id).encode("utf-8")
    matches = [line for line in payload.splitlines() if line.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError("frozen dataset did not yield exactly one selected row")
    line = matches[0]
    row = json.loads(line)
    if row.get("instance_id") != target_id:
        raise RuntimeError("selected row identity mismatch")
    return line + b"\n", row


def _one_feature(payload: bytes, target_id: str) -> bytes:
    text = payload.decode("utf-8")
    key = json.dumps(target_id)
    start = text.find(key)
    if start < 0 or text.find(key, start + len(key)) >= 0:
        raise RuntimeError("feature definition target is absent or duplicated")
    colon = text.find(":", start + len(key))
    value_start = colon + 1
    while value_start < len(text) and text[value_start].isspace():
        value_start += 1
    feature, _ = json.JSONDecoder().raw_decode(text, value_start)
    if not isinstance(feature, str):
        raise RuntimeError("selected feature definition is not Dockerfile text")
    return _canonical({target_id: feature})


def run(args: argparse.Namespace) -> dict[str, Any]:
    repository = Path(args.repository).resolve(strict=True)
    subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", "src", "scripts", "protocols", "tests"],
        cwd=repository,
        check=True,
    )
    implementation_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    exclusion = repository / "protocols/context-dependent-memory-v4-additional-development-exclusions.yaml"
    if _sha(exclusion.read_bytes()) != EXCLUSION_PROTOCOL_SHA256:
        raise RuntimeError("additional development exclusion protocol changed")
    target_id = args.target_id
    if target_id not in TARGETS:
        raise RuntimeError("target infrastructure is not prospectively bound")
    if EXTENSION_IDS.index(target_id) + 1 != args.logical_position:
        raise RuntimeError("extension target logical position mismatch")
    config = TARGETS[target_id]
    date.fromisoformat(str(config["target_b_date_utc"]))

    susvibes = Path(args.susvibes_root).resolve(strict=True)
    runtime = Path(args.runtime_root).resolve(strict=True)
    sources_v1 = Path(args.sources_v1_root).resolve(strict=True)
    sources_v2 = Path(args.sources_v2_root).resolve(strict=True)
    output_root = Path(args.output_root).resolve()
    output = output_root / f"{args.logical_position:02d}-{target_id}"
    if output.exists():
        raise FileExistsError(f"refusing to overwrite extension evidence: {output}")
    output.mkdir(parents=True)
    public = output / "public"
    sealed = output / "sealed"
    public.mkdir()
    sealed.mkdir()

    audit = ContentAccessAudit(
        output / "content-access.sqlite",
        boundaries={
            "REPOSITORY": repository,
            "SUSVIBES": susvibes,
            "RUNTIME": runtime,
            "SOURCES_V1": sources_v1,
            "SOURCES_V2": sources_v2,
            "OUTPUT": output,
        },
        phase="V4_DEVELOPMENT_EXTENSION_LOCK",
        session_id=f"v4-extension-lock-{args.logical_position}",
    )
    dataset = audit.bind_development_file(
        logical_resource="FROZEN_SUSVIBES_DATASET_PREPARATION",
        boundary="SUSVIBES",
        relative_path="datasets/default/susvibes_dataset.jsonl",
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension.prepare_row",
    )
    dataset_payload = audit.read_bytes(
        dataset,
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension.prepare_row",
    )
    row_bytes, row = _one_dataset_row(dataset_payload, target_id)
    feature_source = audit.bind_development_file(
        logical_resource="FROZEN_FEATURE_DEFINITIONS_PREPARATION",
        boundary="SUSVIBES",
        relative_path="susvibes/env_specs/default/dockerfile.json",
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension.prepare_feature",
    )
    feature_bytes = _one_feature(
        audit.read_bytes(
            feature_source,
            target_id=target_id,
            source_id=None,
            caller="lock_confirmatory_v4_extension.prepare_feature",
        ),
        target_id,
    )
    if row.get("language") != "python" or row.get("project") != config["project"]:
        raise RuntimeError("selected row public identity changed")

    b_relative = f"cases/{target_id}/B"
    b_path = runtime / b_relative
    b_hash = tree_sha256(b_path)
    image_relative = str(config["environment_artifact_relative"])
    image_ref = audit.bind_development_file(
        logical_resource="DIGEST_PINNED_BASELINE_IMAGE",
        boundary="RUNTIME",
        relative_path=image_relative,
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension.bind_image",
    )
    if image_ref.sha256 != config["environment_artifact_sha256"]:
        raise RuntimeError("digest-pinned environment artifact hash changed")
    metadata = {
        "b_image_manifest_digest": config["manifest_digest"],
        "b_tree_sha256": b_hash,
        "benchmark_revision": SUSVIBES_REVISION,
        "image_name": config["image"],
        "instance_id": target_id,
        "language": "python",
        "project": row["project"],
    }
    artifacts = {
        "task.statement": str(row["problem_statement"]).encode("utf-8"),
        "public.metadata": json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8") + b"\n",
        "benchmark.row": row_bytes,
        "feature.definition": feature_bytes,
        "target.timestamp": _canonical(
            {
                "date_utc": config["target_b_date_utc"],
                "source": config["timestamp_source"],
                "target_id": target_id,
            }
        ),
    }
    for name, payload in artifacts.items():
        destination = public / name if name.startswith(("task", "public")) else sealed / name
        destination.write_bytes(payload)
    task_ref = audit.bind_development_file(
        logical_resource="TARGET_TASK",
        boundary="OUTPUT",
        relative_path="public/task.statement",
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension",
    )
    metadata_ref = audit.bind_development_file(
        logical_resource="TARGET_PUBLIC_METADATA",
        boundary="OUTPUT",
        relative_path="public/public.metadata",
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension",
    )
    corpus_ref = audit.bind_development_file(
        logical_resource="SOURCE_CORPUS",
        boundary="REPOSITORY",
        relative_path="artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json",
        target_id=target_id,
        source_id=None,
        caller="lock_confirmatory_v4_extension",
    )
    scope_payload = json.dumps(EXTENSION_IDS, separators=(",", ":")).encode("utf-8")
    scope = TargetIdentityScope(
        target_ids=frozenset(EXTENSION_IDS),
        purpose="V4_ADDITIONAL_DEVELOPMENT_ONLY",
        identity_list_sha256=_sha(scope_payload),
        manifest_sha256=EXCLUSION_PROTOCOL_SHA256,
    )
    terminal_reason = "TOP_SOURCE_LOCKED"
    representation: dict[str, Any] | None = None
    rankings: list[dict[str, Any]] = []
    lock: dict[str, Any] | None = None
    try:
        representation, _, rankings, lock = lock_top_source_v4(
            audit=audit,
            public=PublicTargetBundle(
                workspace_root=public,
                task_statement=task_ref,
                public_metadata=metadata_ref,
                baseline_b=TreeRef("TARGET_PUBLIC_B", "RUNTIME", b_relative, b_hash),
            ),
            source_corpus=corpus_ref,
            target_id=target_id,
            target_b_date_utc=str(config["target_b_date_utc"]),
            scope=scope,
        )
    except SourcePairingError as error:
        message = str(error)
        terminal_reason = (
            "AMBIGUOUS_TOP_SOURCE"
            if "AMBIGUOUS" in message
            else "NO_SOURCE_PASSES_HARD_GATES"
        )
    if lock is not None:
        (sealed / "pair.lock").write_bytes(_canonical(lock))
    if representation is not None:
        (public / "target.representation").write_bytes(_canonical(representation))
        audit.bind_development_file(
            logical_resource="B_ONLY_TARGET_REPRESENTATION",
            boundary="OUTPUT",
            relative_path="public/target.representation",
            target_id=target_id,
            source_id=None if lock is None else str(lock["top_source_id"]),
            caller="lock_confirmatory_v4_extension.persist_representation",
        )
    record = {
        "schema": "cmpilot-v4-extension-pair-lock-v1",
        "development_only": True,
        "logical_position": args.logical_position,
        "target_id": target_id,
        "implementation_commit": implementation_commit,
        "exclusion_protocol_commit": "c7b6091e786773235e2f215c456cc83fd5f7ff31",
        "exclusion_protocol_sha256": EXCLUSION_PROTOCOL_SHA256,
        "benchmark_revision": SUSVIBES_REVISION,
        "image_manifest_digest": config["manifest_digest"],
        "environment_artifact_sha256": config["environment_artifact_sha256"],
        "b_tree_sha256": b_hash,
        "target_b_date_utc": config["target_b_date_utc"],
        "target_b_timestamp_source": config["timestamp_source"],
        "cue_classification": classify_task_statement(str(row["problem_statement"]))[
            "classification"
        ],
        "target_representation_sha256": None
        if representation is None
        else stable_record_hash(representation),
        "full_rankings_sha256": None if not rankings else stable_record_hash(rankings),
        "top_source_id": None if lock is None else lock["top_source_id"],
        "pair_hash": None if lock is None else lock["pair_hash"],
        "terminal_reason": terminal_reason,
        "rank_2_fallback": False,
        "source_replacement": False,
        "audit_event_count": len(audit.events()),
        "audit_chain_sha256": audit.verify_chain(),
        "unseen_confirmatory_targets_screened": 0,
        "evaluated_model_runs": 0,
        "gpu_used": False,
    }
    (output / "pair-lock-evidence.yaml").write_text(render_yaml(record), encoding="utf-8")
    return record


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repository", type=Path, default=Path.cwd())
    value.add_argument("--target-id", required=True)
    value.add_argument("--logical-position", type=int, required=True)
    value.add_argument("--susvibes-root", type=Path, required=True)
    value.add_argument("--runtime-root", type=Path, required=True)
    value.add_argument("--sources-v1-root", type=Path, required=True)
    value.add_argument("--sources-v2-root", type=Path, required=True)
    value.add_argument("--output-root", type=Path, required=True)
    return value


def main() -> int:
    print(render_yaml(run(parser().parse_args())), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

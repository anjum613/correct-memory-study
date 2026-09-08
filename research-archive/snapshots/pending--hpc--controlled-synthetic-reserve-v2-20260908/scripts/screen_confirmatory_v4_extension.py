#!/usr/bin/env python3
"""Run one frozen V4 extension pair through the production sealed provider."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.development_validation_v3 import render_yaml
from cmpilot.production_v4 import (
    ProductionSealedEvidenceProvider,
    ScreeningLedgerV4,
    SealedPairBundle,
)
from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import SUSVIBES_REVISION
from cmpilot.target_runtime_v4 import BenchmarkRowBinding, ExecutionEnvironment


EXTENSION_IDS = (
    "vyperlang__vyper_851f7a1b3aa2a36fd041e3d0ed38f9355a58c8ae",
    "openstack__aodh_149d3ad2193b4d17df801f82a0a6be62dba564db",
    "urllib3__urllib3_a74c9cfbaed9f811e7563cfc3dce894928e0221a",
    "tensorflow__tensorflow_dbdd98c37bc25249e8f288bd30d01e118a7b4498",
    "django__django_1f2dd37f6fcefdd10ed44cb233b2e62b520afb38",
)
TARGETS: dict[str, dict[str, Any]] = {
    EXTENSION_IDS[0]: {
        "position": 1,
        "source_id": "src-aio-fernet-save-session",
        "pair_hash": "6e6cd0bc43ed58834ef5c5a9383f8fb38af4f79b3fabcfcfd97db4b2cb4f7f20",
        "b_sha256": "3180cb7a376e2743dd5d916642c6dc9e0e6c5a3f62c8f841f342b3df8702abdb",
        "u_sha256": "df54b1a448b76df93908e9eaa0f2ad03cd5bce4ec89267334dfca8cbe3cddc0c",
        "r_sha256": "9bd158f552c5fef252d0c8f164b613b75fbf5caa20dafc71133f90a12b6d10fc",
        "row_sha256": "d52db95b971f08f20bb1ebf1c7eaa9e7868f44c9c9fb82bbcdfbe01b58341c82",
        "mask_patch_sha256": "dde7f294a0631a8faa064c8265bb444307ce5809b2605520d080746d367d668e",
        "golden_patch_sha256": "42fca10ee21d5b5fdd95c3c70edd819033864b2ca16f94100ad5a372305bd817",
        "security_patch_sha256": "0dc7e94b3b6913073a5a08f99340b5bd76b5a0203649551ce6375cd4530225ad",
        "test_patch_sha256": "7e27b7c8fee46825896b5f5d8221d8d6bad2f01f6c9fecef9e9ecdeffe8fc6b2",
        "image_manifest_digest": "sha256:f9e7219d2912d2835ba3fc7ea69b3ece4182438941b0c662a0d856e6a7ec6f71",
        "pstar": None,
    }
}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bind(
    audit: ContentAccessAudit,
    *,
    logical: str,
    boundary: str,
    relative: str,
    target_id: str,
    source_id: str,
) -> ArtifactRef:
    return audit.bind_development_file(
        logical_resource=logical,
        boundary=boundary,
        relative_path=relative,
        target_id=target_id,
        source_id=source_id,
        caller="screen_confirmatory_v4_extension",
    )


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
    target_id = args.target_id
    if target_id not in TARGETS:
        raise RuntimeError("target has no immutable production-screening binding")
    config = TARGETS[target_id]
    position = int(config["position"])
    if position != EXTENSION_IDS.index(target_id) + 1:
        raise RuntimeError("target violates the frozen extension order")
    source_id = str(config["source_id"])
    pair_hash = str(config["pair_hash"])

    runtime = Path(args.runtime_root).resolve(strict=True)
    extension = Path(args.extension_root).resolve(strict=True)
    target_root = extension / f"{position:02d}-{target_id}"
    decision_path = target_root / "screen-decision.yaml"
    if decision_path.exists():
        raise FileExistsError("refusing to overwrite a terminal screening decision")
    scratch = runtime / "production-screen-scratch"
    scratch.mkdir(exist_ok=True)
    audit = ContentAccessAudit(
        target_root / "production-content-access.sqlite",
        boundaries={
            "REPOSITORY": repository,
            "RUNTIME": runtime,
            "TARGET": target_root,
        },
        phase="V4_DEVELOPMENT_EXTENSION_PRODUCTION_SCREEN",
        session_id=f"v4-extension-production-screen-{position}",
    )
    task = _bind(
        audit,
        logical="TARGET_TASK",
        boundary="TARGET",
        relative="public/task.statement",
        target_id=target_id,
        source_id=source_id,
    )
    lock = _bind(
        audit,
        logical="PAIR_LOCK",
        boundary="TARGET",
        relative="sealed/pair.lock",
        target_id=target_id,
        source_id=source_id,
    )
    row = _bind(
        audit,
        logical="BENCHMARK_ROW",
        boundary="TARGET",
        relative="sealed/benchmark.row",
        target_id=target_id,
        source_id=source_id,
    )
    feature = _bind(
        audit,
        logical="FEATURE_TEST_DEFINITION",
        boundary="TARGET",
        relative="sealed/feature.definition",
        target_id=target_id,
        source_id=source_id,
    )
    timestamp = _bind(
        audit,
        logical="TARGET_TIMESTAMP",
        boundary="TARGET",
        relative="sealed/target.timestamp",
        target_id=target_id,
        source_id=source_id,
    )
    corpus = _bind(
        audit,
        logical="SOURCE_CORPUS",
        boundary="REPOSITORY",
        relative="artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json",
        target_id=target_id,
        source_id=source_id,
    )
    binding = BenchmarkRowBinding(
        target_id=target_id,
        row_sha256=str(config["row_sha256"]),
        benchmark_revision=SUSVIBES_REVISION,
        b_tree_sha256=str(config["b_sha256"]),
        u_tree_sha256=str(config["u_sha256"]),
        r_tree_sha256=str(config["r_sha256"]),
        mask_patch_sha256=str(config["mask_patch_sha256"]),
        golden_patch_sha256=str(config["golden_patch_sha256"]),
        security_patch_sha256=str(config["security_patch_sha256"]),
        test_patch_sha256=str(config["test_patch_sha256"]),
    )
    case = runtime / "cases" / target_id
    bundle = SealedPairBundle(
        task_statement=task,
        pair_lock=lock,
        source_corpus=corpus,
        dataset=row,
        baseline_b=TreeRef(
            "TARGET_B", "RUNTIME", f"cases/{target_id}/B", binding.b_tree_sha256
        ),
        feature_definition=feature,
        target_binding=binding,
        target_environment=ExecutionEnvironment(
            argv_prefix=(
                str(repository / "scripts/susvibes_rootfs_exec.sh"),
                str(case / "rootfs"),
            ),
            environment_identity="SUSVIBES_V1_PINNED_ROOTFS:"
            + str(config["image_manifest_digest"]),
            timeout_seconds=1200,
        ),
        pstar=config["pstar"],
        scratch_parent=scratch,
        target_timestamp=timestamp,
    )
    provider = ProductionSealedEvidenceProvider(
        audit=audit,
        bundles={(target_id, source_id, pair_hash): bundle},
        sealed_evidence_database=target_root / "sealed-evidence.sqlite",
    )
    ledger = ScreeningLedgerV4(
        extension / "screening-ledger.sqlite", ordered_targets=EXTENSION_IDS
    )
    ledger.record_attempt(
        logical_position=position,
        target_id=target_id,
        stage="COMPLETE_PRODUCTION_PATH",
        status="STARTED",
        evidence_sha256=pair_hash,
    )
    response = provider.load(
        target_id=target_id,
        top_source_id=source_id,
        pair_hash=pair_hash,
    )
    decision = "ELIGIBLE" if response["decision"] == "ACCEPT" else (
        "TECHNICAL_INVALID"
        if response["terminal_reason"] == "TARGET_TECHNICAL_INVALID"
        else "REJECT"
    )
    terminal = ledger.record_decision(
        logical_position=position,
        target_id=target_id,
        decision=decision,
        terminal_reason=str(response["terminal_reason"]),
        evidence_sha256=stable_record_hash(response),
    )
    record = {
        "schema": "cmpilot-v4-development-extension-screen-decision-v1",
        "development_only": True,
        "logical_position": position,
        "target_id": target_id,
        "top_source_id": source_id,
        "pair_hash": pair_hash,
        "implementation_commit": implementation_commit,
        "response": response,
        "terminal_ledger_record": terminal,
        "content_access_event_count": len(audit.events()),
        "content_access_chain_sha256": audit.verify_chain(),
        "sealed_evidence_database_sha256": _sha(
            (target_root / "sealed-evidence.sqlite").read_bytes()
        ),
        "unseen_confirmatory_targets_screened": 0,
        "evaluated_model_runs": 0,
        "gpu_used": False,
    }
    decision_path.write_text(render_yaml(record), encoding="utf-8")
    return record


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repository", type=Path, default=Path.cwd())
    value.add_argument("--target-id", required=True)
    value.add_argument("--runtime-root", type=Path, required=True)
    value.add_argument("--extension-root", type=Path, required=True)
    return value


def main() -> int:
    print(render_yaml(run(parser().parse_args())), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

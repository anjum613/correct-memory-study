#!/usr/bin/env python3
"""Run the bounded V4 production path on the five excluded development targets."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from cmpilot.artifact_evidence_v4 import (
    ArtifactPredicate,
    FindingSpec,
    PstarEvidenceSpec,
    SourceExecutionSpec,
)
from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.development_validation_v3 import render_yaml
from cmpilot.production_v4 import (
    ProductionSealedEvidenceProvider,
    PublicTargetBundle,
    SealedPairBundle,
    load_frozen_source_corpus_v4,
    lock_top_source_v4,
)
from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION
from cmpilot.target_identity_v3 import TargetIdentityScope
from cmpilot.target_runtime_v4 import BenchmarkRowBinding, ExecutionEnvironment


FROZEN_LOCKS = {
    DEVELOPMENT_IDS[0]: (
        "src-aio-fernet-load-session",
        "aea73ec3b6b8bb289b60204a344c6279c1bfbb7a794b1852c729376c921ec2f4",
    ),
    DEVELOPMENT_IDS[1]: (
        "src-v2-buildbot-gerrit-defaultsummarycb-71d61463baee",
        "d13f52fb28fefbca617689300929f62b70dc1a98215bae04f1542e278e5c7eac",
    ),
    DEVELOPMENT_IDS[2]: (
        "src-wagtail-document-link-expand",
        "47a1e73870a306d4c4747a5d0e21e120bd66d863c3a989cee4da9f43852cb9a6",
    ),
    DEVELOPMENT_IDS[3]: (
        "src-django-constant-time-compare",
        "cc3fd6d9d5ef58f2fe7ce83921ec5340b8eddcf3f02fbefa08a68337a67130f1",
    ),
    DEVELOPMENT_IDS[4]: (
        "src-requests-resolve-proxies",
        "74c6b627ecfa7574575fb135d1d3a343babc1cff66d7d566db9c70bf2381a749",
    ),
}


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_row(row: Mapping[str, Any]) -> bytes:
    return json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _bind(
    audit: ContentAccessAudit,
    *,
    logical: str,
    boundary: str,
    relative: str,
    target_id: str,
    source_id: str | None = None,
) -> ArtifactRef:
    return audit.bind_development_file(
        logical_resource=logical,
        boundary=boundary,
        relative_path=relative,
        target_id=target_id,
        source_id=source_id,
        caller="run_confirmatory_v4_development",
    )


def _aio_pstar(
    *,
    audit: ContentAccessAudit,
    source: Mapping[str, Any],
    target_id: str,
    runtime_root: Path,
    launcher: Path,
) -> PstarEvidenceSpec:
    source_id = str(source["source_id"])
    source_code = _bind(
        audit,
        logical="SOURCE_CODE",
        boundary="SOURCES_V1",
        relative="aiohttp-session/aiohttp_session/cookie_storage.py",
        target_id=target_id,
        source_id=source_id,
    )
    source_test = _bind(
        audit,
        logical="SOURCE_TEST",
        boundary="SOURCES_V1",
        relative="aiohttp-session/tests/test_encrypted_cookie_storage.py",
        target_id=target_id,
        source_id=source_id,
    )
    target_code_path = f"cases/{target_id}/B/aiohttp_session/__init__.py"
    target_code = _bind(
        audit,
        logical="TARGET_CODE",
        boundary="RUNTIME",
        relative=target_code_path,
        target_id=target_id,
        source_id=source_id,
    )
    target_task = _bind(
        audit,
        logical="TARGET_TASK_PSTAR",
        boundary="PUBLIC",
        relative=f"{target_id}/task.md",
        target_id=target_id,
        source_id=source_id,
    )
    security_relative = (
        f"cases/{target_id}/firewall/oracle_sealed/{target_id}/security_patch.patch"
    )
    target_patch = _bind(
        audit,
        logical="TARGET_SECURITY_PATCH",
        boundary="RUNTIME",
        relative=security_relative,
        target_id=target_id,
        source_id=source_id,
    )
    pstar = source["focal_source_safety"]["pstar"]
    source_tree = Path(source["source_build"]["command"][2])
    source_rootfs = Path(source["source_build"]["command"][1])
    return PstarEvidenceSpec(
        proposition_text=str(pstar["proposition"]),
        ontology_class=str(pstar["ontology_class"]),
        source_objects=tuple(str(value) for value in pstar["observable_objects"]),
        target_objects=("session mapping", "session age"),
        operation=str(pstar["operation"]),
        boundary_or_condition="await asyncio.sleep(MAX_AGE + 1)",
        level="A",
        target_status="UNJUSTIFIED",
        source_artifacts=(("source_code", source_code), ("source_test", source_test)),
        target_artifacts=(
            ("target_code", target_code),
            ("target_task", target_task),
            ("target_security_patch", target_patch),
        ),
        source_code_artifact="source_code",
        source_test_artifact="source_test",
        source_boundary_predicates=(
            ArtifactPredicate(
                "source_test", "CONTAINS_EXACT", "await asyncio.sleep(MAX_AGE + 1)"
            ),
        ),
        findings=(
            FindingSpec(
                "TARGET_PSTAR_MISMATCH",
                (ArtifactPredicate("target_code", "ABSENT_EXACT", "ttl=self.max_age"),),
            ),
            FindingSpec(
                "MATERIAL_PROCEDURAL_RELEVANCE",
                (
                    ArtifactPredicate("source_code", "CONTAINS_EXACT", "Session"),
                    ArtifactPredicate("target_task", "CONTAINS_EXACT", "session"),
                ),
            ),
            FindingSpec(
                "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
                (
                    ArtifactPredicate("source_code", "CONTAINS_EXACT", "load_session"),
                    ArtifactPredicate("target_code", "CONTAINS_EXACT", "Session"),
                ),
            ),
            FindingSpec(
                "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY",
                (
                    ArtifactPredicate(
                        "target_security_patch",
                        "PATCH_TOUCHES_EXACT_PATHS",
                        "aiohttp_session/__init__.py",
                    ),
                ),
            ),
        ),
        source_execution=SourceExecutionSpec(
            tree=TreeRef(
                "SOURCE_TREE",
                "SOURCES_V1",
                source_tree.name,
                str(source["reconstruction"]["tree_sha256"]),
            ),
            argv=(
                str(launcher),
                str(source_rootfs),
                "{tree}",
                "/bin/bash",
                "-lc",
                "cd /project && python -m pytest -q tests/test_encrypted_cookie_storage.py -k test_fernet_ttl",
            ),
            environment_identity=str(source["source_environment_hash"]),
        ),
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
    susvibes = Path(args.susvibes_root).resolve(strict=True)
    runtime = Path(args.runtime_root).resolve(strict=True)
    public = Path(args.public_root).resolve(strict=True)
    sources_v1 = Path(args.sources_v1_root).resolve(strict=True)
    sources_v2 = Path(args.sources_v2_root).resolve(strict=True)
    output = Path(args.output_root).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite V4 evidence: {output}")
    output.mkdir(parents=True)
    scratch = output / "scratch"
    scratch.mkdir()
    pair_locks = output / "pair-locks"
    pair_locks.mkdir()
    audit = ContentAccessAudit(
        output / "content-access.sqlite",
        boundaries={
            "REPOSITORY": repository,
            "SUSVIBES": susvibes,
            "RUNTIME": runtime,
            "PUBLIC": public,
            "SOURCES_V1": sources_v1,
            "SOURCES_V2": sources_v2,
            "OUTPUT": output,
        },
        phase="V4_DEVELOPMENT_ORIGINAL_FIVE",
        session_id="v4-original-five",
    )
    corpus_ref = _bind(
        audit,
        logical="SOURCE_CORPUS",
        boundary="REPOSITORY",
        relative="artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json",
        target_id=DEVELOPMENT_IDS[0],
    )
    matcher_ref = _bind(
        audit,
        logical="FROZEN_MATCHER_DEVELOPMENT_RANKINGS",
        boundary="REPOSITORY",
        relative="artifacts/context-dependent-memory-source-pairing-v2/matcher-v2-development-rankings.json",
        target_id=DEVELOPMENT_IDS[0],
    )
    reproducibility_ref = _bind(
        audit,
        logical="SUSVIBES_REPRODUCIBILITY",
        boundary="REPOSITORY",
        relative="artifacts/context-dependent-memory-susvibes-feasibility/reproducibility-manifest.json",
        target_id=DEVELOPMENT_IDS[0],
    )
    dataset_ref = _bind(
        audit,
        logical="SUSVIBES_DATASET",
        boundary="SUSVIBES",
        relative="datasets/default/susvibes_dataset.jsonl",
        target_id=DEVELOPMENT_IDS[0],
    )
    feature_ref = _bind(
        audit,
        logical="FEATURE_TEST_DEFINITION",
        boundary="SUSVIBES",
        relative="susvibes/env_specs/default/dockerfile.json",
        target_id=DEVELOPMENT_IDS[0],
    )
    matcher = json.loads(
        audit.read_bytes(
            matcher_ref,
            target_id=DEVELOPMENT_IDS[0],
            source_id=None,
            caller="run_confirmatory_v4_development",
        )
    )
    epochs = {
        row["target_id"]: row["target_b_timestamp_epoch"] for row in matcher["targets"]
    }
    reproducibility = json.loads(
        audit.read_bytes(
            reproducibility_ref,
            target_id=DEVELOPMENT_IDS[0],
            source_id=None,
            caller="run_confirmatory_v4_development",
        )
    )
    reproducibility_rows = {row["instance_id"]: row for row in reproducibility["cases"]}
    dataset_payload = audit.read_bytes(
        dataset_ref,
        target_id=DEVELOPMENT_IDS[0],
        source_id=None,
        caller="run_confirmatory_v4_development",
    )
    rows = {
        row["instance_id"]: row
        for raw in dataset_payload.splitlines()
        if raw.strip()
        for row in [json.loads(raw)]
        if row["instance_id"] in DEVELOPMENT_IDS
    }
    entries = load_frozen_source_corpus_v4(
        audit, corpus_ref, target_id=DEVELOPMENT_IDS[0]
    )
    entries_by_id = {entry["source_id"]: entry for entry in entries}
    results = []
    scope = TargetIdentityScope.development_fixtures()
    launcher = repository / "scripts/susvibes_rootfs_exec.sh"
    for target_id in DEVELOPMENT_IDS:
        workspace = public / target_id
        task_ref = _bind(
            audit,
            logical="TARGET_TASK",
            boundary="PUBLIC",
            relative=f"{target_id}/task.md",
            target_id=target_id,
        )
        metadata_ref = _bind(
            audit,
            logical="TARGET_PUBLIC_METADATA",
            boundary="PUBLIC",
            relative=f"{target_id}/public-metadata.json",
            target_id=target_id,
        )
        metadata = json.loads(
            audit.read_bytes(
                metadata_ref,
                target_id=target_id,
                source_id=None,
                caller="run_confirmatory_v4_development",
            )
        )
        public_bundle = PublicTargetBundle(
            workspace_root=workspace,
            task_statement=task_ref,
            public_metadata=metadata_ref,
            baseline_b=TreeRef(
                "TARGET_PUBLIC_B",
                "PUBLIC",
                f"{target_id}/repository",
                metadata["b_tree_sha256"],
            ),
        )
        day = datetime.fromtimestamp(epochs[target_id], timezone.utc).date().isoformat()
        _, _, _, lock = lock_top_source_v4(
            audit=audit,
            public=public_bundle,
            source_corpus=corpus_ref,
            target_id=target_id,
            target_b_date_utc=day,
            scope=scope,
        )
        expected_source, expected_hash = FROZEN_LOCKS[target_id]
        if (lock["top_source_id"], lock["pair_hash"]) != (
            expected_source,
            expected_hash,
        ):
            raise RuntimeError("V4 attempted to change an original source lock")
        lock_path = pair_locks / f"{target_id}.lock"
        lock_path.write_bytes(
            json.dumps(lock, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        lock_ref = _bind(
            audit,
            logical="PAIR_LOCK",
            boundary="OUTPUT",
            relative=lock_path.relative_to(output).as_posix(),
            target_id=target_id,
            source_id=expected_source,
        )
        row = rows[target_id]
        reproduction = reproducibility_rows[target_id]
        binding = BenchmarkRowBinding(
            target_id=target_id,
            row_sha256=_sha(_canonical_row(row)),
            benchmark_revision=SUSVIBES_REVISION,
            b_tree_sha256=reproduction["B_sha256"],
            u_tree_sha256=reproduction["U_sha256"],
            r_tree_sha256=reproduction["R_sha256"],
            mask_patch_sha256=_sha(row["mask_patch"].encode("utf-8")),
            golden_patch_sha256=_sha(row["golden_patch"].encode("utf-8")),
            security_patch_sha256=_sha(row["security_patch"].encode("utf-8")),
            test_patch_sha256=_sha(row["test_patch"].encode("utf-8")),
        )
        pstar = (
            _aio_pstar(
                audit=audit,
                source=entries_by_id[expected_source],
                target_id=target_id,
                runtime_root=runtime,
                launcher=launcher,
            )
            if target_id == DEVELOPMENT_IDS[0]
            else None
        )
        case = runtime / "cases" / target_id
        bundle = SealedPairBundle(
            task_statement=task_ref,
            pair_lock=lock_ref,
            source_corpus=corpus_ref,
            dataset=dataset_ref,
            baseline_b=TreeRef(
                "TARGET_B",
                "RUNTIME",
                f"cases/{target_id}/B",
                binding.b_tree_sha256,
            ),
            feature_definition=feature_ref,
            target_binding=binding,
            target_environment=ExecutionEnvironment(
                argv_prefix=(str(launcher), str(case / "rootfs")),
                environment_identity=(
                    "SUSVIBES_V1_PINNED_ROOTFS:"
                    + str(reproduction["container_manifest_digest"])
                ),
                timeout_seconds=1200,
            ),
            pstar=pstar,
            scratch_parent=scratch,
        )
        provider = ProductionSealedEvidenceProvider(
            audit=audit,
            bundles={(target_id, expected_source, expected_hash): bundle},
        )
        response = provider.load(
            target_id=target_id,
            top_source_id=expected_source,
            pair_hash=expected_hash,
        )
        results.append(
            {
                "target_id": target_id,
                "top_source_id": expected_source,
                "pair_hash": expected_hash,
                "source_lock_unchanged": True,
                "response": response,
            }
        )
    record = {
        "schema": "cmpilot-v4-original-development-validation-v1",
        "development_only": True,
        "protocol_commit": "36f3b7564d4c537977b1fd9c18a54014dcc5c783",
        "implementation_commit": implementation_commit,
        "benchmark_revision": SUSVIBES_REVISION,
        "source_corpus_sha256": (
            "1b4f9584c88317d1a523ce24bc4ef27aa4a1f8317cbf804e41de4816f9b3df2c"
        ),
        "original_development_targets": list(DEVELOPMENT_IDS),
        "results": results,
        "original_development_all_yes": sum(
            row["response"]["decision"] == "ACCEPT" for row in results
        ),
        "real_acceptance_path_validated": any(
            row["response"]["decision"] == "ACCEPT" for row in results
        ),
        "unseen_confirmatory_targets_screened": 0,
        "evaluated_model_runs": 0,
        "gpu_used": False,
        "audit_event_count": len(audit.events()),
        "audit_chain_sha256": audit.verify_chain(),
    }
    (output / "original-five-validation.yaml").write_text(
        render_yaml(record), encoding="utf-8"
    )
    return record


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repository", type=Path, default=Path.cwd())
    value.add_argument("--susvibes-root", type=Path, required=True)
    value.add_argument("--runtime-root", type=Path, required=True)
    value.add_argument("--public-root", type=Path, required=True)
    value.add_argument("--sources-v1-root", type=Path, required=True)
    value.add_argument("--sources-v2-root", type=Path, required=True)
    value.add_argument("--output-root", type=Path, required=True)
    return value


def main() -> int:
    result = run(parser().parse_args())
    print(render_yaml(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

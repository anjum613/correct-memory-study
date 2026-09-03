from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.production_v4 import (
    FROZEN_SOURCE_CORPUS_SHA256,
    ProductionSealedEvidenceProvider,
    ProductionV4Error,
    ScreeningLedgerV4,
    SealedPairBundle,
    frozen_target_order,
    load_frozen_source_corpus_v4,
)
from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION, tree_sha256
from cmpilot.target_runtime_v4 import BenchmarkRowBinding, ExecutionEnvironment


ROOT = Path(__file__).resolve().parents[1]
TARGET = "development__production_" + "d" * 40
SOURCE = "src-production-test"


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_source_corpus_hash_is_enforced_on_every_load(tmp_path: Path) -> None:
    artifact = ROOT / "artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json"
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"REPOSITORY": ROOT},
        phase="V4_DEVELOPMENT",
    )
    ref = ArtifactRef(
        "SOURCE_CORPUS",
        "REPOSITORY",
        artifact.relative_to(ROOT).as_posix(),
        _sha(artifact.read_bytes()),
    )
    first = load_frozen_source_corpus_v4(audit, ref, target_id=TARGET)
    second = load_frozen_source_corpus_v4(audit, ref, target_id=TARGET)
    assert len(first) == len(second) == 50
    assert stable_record_hash(sorted(first, key=lambda row: row["source_id"])) == FROZEN_SOURCE_CORPUS_SHA256
    assert [event["logical_resource"] for event in audit.events()] == [
        "SOURCE_CORPUS",
        "SOURCE_CORPUS",
    ]

    changed_root = tmp_path / "changed"
    changed_root.mkdir()
    value = json.loads(artifact.read_text())
    value["entries"][0]["language"] = "changed"
    payload = json.dumps(value).encode()
    (changed_root / "corpus.json").write_bytes(payload)
    changed_audit = ContentAccessAudit(
        tmp_path / "changed.sqlite",
        boundaries={"CHANGED": changed_root},
        phase="V4_DEVELOPMENT",
    )
    with pytest.raises(ProductionV4Error, match="canonical source corpus hash"):
        load_frozen_source_corpus_v4(
            changed_audit,
            ArtifactRef("SOURCE_CORPUS", "CHANGED", "corpus.json", _sha(payload)),
            target_id=TARGET,
        )


def test_production_provider_executes_frozen_cue_gate_before_sealed_target_data(
    tmp_path: Path,
) -> None:
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    task = b"Implement the feature and prevent credential leak attacks.\n"
    (frozen / "task.md").write_bytes(task)
    lock_body = {
        "target_id": TARGET,
        "top_source_id": SOURCE,
        "top_one": True,
        "rank_2_fallback": False,
        "focal_safety_evaluated_pre_lock": False,
    }
    pair_hash = stable_record_hash(lock_body)
    lock = {**lock_body, "pair_hash": pair_hash}
    lock_bytes = json.dumps(lock, sort_keys=True).encode()
    (frozen / "lock.json").write_bytes(lock_bytes)
    (frozen / "unused").write_bytes(b"unused")
    empty = frozen / "empty"
    empty.mkdir()
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"FROZEN": frozen},
        phase="V4_DEVELOPMENT",
    )
    unused = ArtifactRef("UNUSED", "FROZEN", "unused", _sha(b"unused"))
    bundle = SealedPairBundle(
        task_statement=ArtifactRef("TASK", "FROZEN", "task.md", _sha(task)),
        pair_lock=ArtifactRef("PAIR_LOCK", "FROZEN", "lock.json", _sha(lock_bytes)),
        source_corpus=unused,
        dataset=unused,
        baseline_b=TreeRef("B", "FROZEN", "empty", tree_sha256(empty)),
        feature_definition=unused,
        target_binding=BenchmarkRowBinding(
            target_id=TARGET,
            row_sha256="0" * 64,
            benchmark_revision=SUSVIBES_REVISION,
            b_tree_sha256="1" * 64,
            u_tree_sha256="2" * 64,
            r_tree_sha256="3" * 64,
            mask_patch_sha256="4" * 64,
            golden_patch_sha256="5" * 64,
            security_patch_sha256="6" * 64,
            test_patch_sha256="7" * 64,
        ),
        target_environment=ExecutionEnvironment(),
        pstar=object(),  # type: ignore[arg-type]
        scratch_parent=tmp_path,
    )
    provider = ProductionSealedEvidenceProvider(
        audit=audit, bundles={(TARGET, SOURCE, pair_hash): bundle}
    )
    result = provider.load(target_id=TARGET, top_source_id=SOURCE, pair_hash=pair_hash)
    assert result == {
        "decision": "REJECT",
        "review_answers": {question: "NO" for question in result["review_answers"]},
        "evidence_hashes": {},
        "terminal_reason": "TASK_STATEMENT_CUE_REJECT",
        "pair_hash": pair_hash,
    }
    assert [event["logical_resource"] for event in audit.events()] == ["TASK", "PAIR_LOCK"]


def test_frozen_target_order_excludes_all_development_ids_and_is_deterministic() -> None:
    additional = "repo__additional_" + "e" * 40
    candidates = [
        *DEVELOPMENT_IDS,
        additional,
        "repo__one_" + "1" * 40,
        "repo__two_" + "2" * 40,
        "repo__three_" + "3" * 40,
    ]
    observed = frozen_target_order(
        tuple(reversed(candidates)), additional_development_exclusions=(additional,)
    )
    expected = tuple(
        sorted(
            candidates[-3:],
            key=lambda value: (
                hashlib.sha256(
                    b"cmpilot-confirmatory-target-order-v2\0" + value.encode()
                ).digest(),
                value,
            ),
        )
    )
    assert observed == expected
    assert frozen_target_order(candidates, additional_development_exclusions=(additional,)) == expected


def test_durable_stopping_terminal_reason_and_ordered_publication_barrier(
    tmp_path: Path,
) -> None:
    targets = tuple(f"repo__target-{index}_" + f"{index:040x}" for index in range(1, 14))
    ledger = ScreeningLedgerV4(tmp_path / "screening.sqlite", ordered_targets=targets)
    ledger.record_attempt(
        logical_position=1,
        target_id=targets[0],
        stage="CUE_GATE",
        status="PASS",
        evidence_sha256="a" * 64,
    )
    with pytest.raises(ProductionV4Error, match="skip an earlier|publication barrier"):
        ledger.record_decision(
            logical_position=2,
            target_id=targets[1],
            decision="REJECT",
            terminal_reason="TASK_STATEMENT_CUE_REJECT",
            evidence_sha256="b" * 64,
        )
    for position, target in enumerate(targets[:12], 1):
        ledger.record_decision(
            logical_position=position,
            target_id=target,
            decision="ELIGIBLE",
            terminal_reason="ELIGIBLE_PAIR_FROZEN",
            evidence_sha256=hashlib.sha256(target.encode()).hexdigest(),
        )
    assert ledger.should_stop() is True
    assert ledger.stop_reason() == "TARGET_N_REACHED"
    assert ledger.decisions()[-1]["eligible_count"] == 12
    with pytest.raises(ProductionV4Error, match="already stopped"):
        ledger.record_decision(
            logical_position=13,
            target_id=targets[12],
            decision="REJECT",
            terminal_reason="SEALED_PAIR_REVIEW_REJECT",
            evidence_sha256="c" * 64,
        )
    with sqlite3.connect(ledger.database) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute("UPDATE screening_decision SET terminal_reason = 'SOURCE_SAFETY_REJECT'")


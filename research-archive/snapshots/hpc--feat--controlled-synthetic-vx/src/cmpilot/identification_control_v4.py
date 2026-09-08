"""Model-free non-vacuity controls for the frozen V4 identification contract."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

import yaml

from cmpilot.artifact_evidence_v4 import (
    ArtifactEvidenceV4Error,
    ArtifactPredicate,
    FindingSpec,
    PstarEvidenceSpec,
    SourceExecutionSpec,
    verify_artifact_bound_pstar,
)
from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.memory_lifecycle import (
    audit_memory_packet,
    context_budget_record,
    lexical_tokens,
    render_memory_packet,
)
from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.production_v4 import _GloballyAuditedBReader
from cmpilot.source_pairing import (
    classify_task_statement,
    source_feature_record,
    stable_record_hash,
)
from cmpilot.source_pairing_v3 import (
    enforce_irrelevant_lock_v3,
    enforce_top_source_lock_v3,
    select_irrelevant_memory_v3,
    select_top_source_v3,
)
from cmpilot.source_validation import (
    run_evidence_command,
    validate_source_correct_entry,
)
from cmpilot.susvibes_feasibility import SUSVIBES_REVISION, tree_sha256
from cmpilot.target_identity_v3 import (
    TargetIdentityScope,
    build_b_only_representation_v3,
)
from cmpilot.target_runtime_v4 import (
    BenchmarkRowBinding,
    ExecutionEnvironment,
    execute_target_gates,
)


PINNED_V4_COMMIT = "5b21f286f7832864ca4eca9ee5795e058849b509"
CONTROL_SOURCE_CORPUS_SHA256 = (
    "6b0306eb79e5e12877ddc684ad940018dad73a379b11ed4b3193614c99f91976"
)
CONTROL_FIXTURE_INTEGRITY_SHA256 = (
    "c6472a80ccdba7e8aa3a845b0e557c1c55162f6a5459f1054876f579c330d01e"
)
CONTROL_NAMES = frozenset(
    {
        "positive",
        "target_already_solved",
        "source_not_focally_safe",
    }
)
SCIENTIFIC_LOGIC_SHA256 = {
    "src/cmpilot/artifact_evidence_v4.py": "044b79c952bdbc43413895c99bd9b82f5436298a6d20ae6f7a0a08fff211f1cd",
    "src/cmpilot/content_audit_v4.py": "c692a08204d4943d933c184e066bd95ec858cde8c4749cb99c68d2f0d6616a96",
    "src/cmpilot/production_v4.py": "04e04f7505c6debe4a871507b0a1f25b54c61e17ed715ab6c107885ab9329ff4",
    "src/cmpilot/target_runtime_v4.py": "7c5d9d9651f866f77c365434295700d92309288148aea35d165f88129cb208bf",
    "src/cmpilot/source_pairing.py": "dacffee80bd7b2c5568b7f1f638a67d011607da9d9b203e18d9f65d0177d8679",
    "src/cmpilot/source_pairing_v2.py": "115860a8f12cec891c07b7623cb8226c9d20b8b7e4cd1b859709e843eb29b813",
    "src/cmpilot/source_pairing_v3.py": "4212fb76e96ec9744606c57e18da6538e849ede8f808871f846b364bafc0efe0",
    "src/cmpilot/source_pairing_confirmatory_v2.py": "ed9a6f8738479ccb9339d74d584fd15796a46208bafc9447a280aa50ffd94526",
    "src/cmpilot/source_validation.py": "c6d47deded6645151e3a7ec78d086a7a03bb4b930aa57773cd031319c6fb7fdb",
    "src/cmpilot/target_identity_v3.py": "baf8c43b65c08d6eca1495f786413cd8227e2e24b0ffecf7c65b7099e8f8068e",
    "src/cmpilot/pair_review.py": "5f10b0399a4f534164ee0d38f24e5d223b2ee148feb5ec59bfd8135c17672231",
    "src/cmpilot/pair_review_v3.py": "96e023dfccf7154e24e3a2bbfa067e3c3c14112e5622d28334215a5c18104214",
    "src/cmpilot/source_safety_v3.py": "a3b948f9c5e44e4abac56014ffe063a64b7526ec22418bd4db59412a00699d74",
    "src/cmpilot/target_eligibility_v3.py": "6ab4b3c53a589e3f029695095ad389afafca7a222182b2f28b5d3771ce93a9b7",
    "src/cmpilot/memory_lifecycle.py": "ac9c5f21ae2d0dc0616956016be5078be7f01ee839c4ed822cfe0f439adb5987",
}


class IdentificationControlV4Error(RuntimeError):
    """A control artifact, sequence, or frozen V4 decision invariant failed."""


@dataclass(frozen=True)
class ControlManifests:
    corpus: Mapping[str, Any]
    integrity: Mapping[str, Any]
    corpus_sha256: str
    integrity_sha256: str


@dataclass(frozen=True)
class PreparedControl:
    result: Mapping[str, Any]
    pair_lock: Mapping[str, Any]
    rankings: tuple[Mapping[str, Any], ...]
    source_entries: tuple[Mapping[str, Any], ...]
    relevant_source: Mapping[str, Any]


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _contains_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, Mapping):
        return any(_contains_boolean(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_boolean(item) for item in value)
    return False


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_control_root() -> Path:
    return repository_root() / "controls/v4_identification_nonvacuity"


def verify_scientific_logic_unchanged(root: Path | None = None) -> dict[str, str]:
    repo = repository_root() if root is None else Path(root).resolve(strict=True)
    observed = {
        relative: _sha((repo / relative).read_bytes())
        for relative in SCIENTIFIC_LOGIC_SHA256
    }
    if observed != SCIENTIFIC_LOGIC_SHA256:
        changed = sorted(
            name
            for name, expected in SCIENTIFIC_LOGIC_SHA256.items()
            if observed.get(name) != expected
        )
        raise IdentificationControlV4Error(
            "frozen V4 scientific logic changed: " + ", ".join(changed)
        )
    return observed


def load_control_manifests(control_root: Path) -> ControlManifests:
    root = Path(control_root).resolve(strict=True)
    corpus_bytes = (root / "source-corpus.yaml").read_bytes()
    integrity_bytes = (root / "fixture-integrity.yaml").read_bytes()
    corpus_hash = _sha(corpus_bytes)
    integrity_hash = _sha(integrity_bytes)
    if corpus_hash != CONTROL_SOURCE_CORPUS_SHA256:
        raise IdentificationControlV4Error("control source-corpus hash mismatch")
    if integrity_hash != CONTROL_FIXTURE_INTEGRITY_SHA256:
        raise IdentificationControlV4Error("control fixture-integrity hash mismatch")
    corpus = yaml.safe_load(corpus_bytes)
    integrity = yaml.safe_load(integrity_bytes)
    if not isinstance(corpus, Mapping) or not isinstance(integrity, Mapping):
        raise IdentificationControlV4Error("control manifest is not a mapping")
    if _contains_boolean(corpus) or _contains_boolean(integrity):
        raise IdentificationControlV4Error(
            "control manifests may not supply scientific booleans"
        )
    if corpus.get("pinned_v4_commit") != PINNED_V4_COMMIT:
        raise IdentificationControlV4Error("control corpus V4 pin mismatch")
    if integrity.get("pinned_v4_commit") != PINNED_V4_COMMIT:
        raise IdentificationControlV4Error("control integrity V4 pin mismatch")
    return ControlManifests(corpus, integrity, corpus_hash, integrity_hash)


def _artifact_ref(
    integrity: Mapping[str, Any], relative: str, *, logical: str
) -> ArtifactRef:
    digest = integrity.get("artifacts", {}).get(relative)
    if not isinstance(digest, str):
        raise IdentificationControlV4Error(f"unbound control artifact: {relative}")
    return ArtifactRef(logical, "CONTROL", relative, digest)


def _tree_ref(
    integrity: Mapping[str, Any], relative: str, *, group: str, key: str, logical: str
) -> TreeRef:
    digest = integrity.get(group, {}).get(key)
    if not isinstance(digest, str):
        raise IdentificationControlV4Error(f"unbound control tree: {relative}")
    return TreeRef(logical, "CONTROL", relative, digest)


def _write_generated(root: Path, name: str, payload: bytes, logical: str) -> ArtifactRef:
    path = root / name
    path.write_bytes(payload)
    return ArtifactRef(logical, "GENERATED", name, _sha(payload))


def _diff_patch(before: bytes, after: bytes, relative: str) -> str:
    if before == after:
        raise IdentificationControlV4Error("control patch states must differ")
    diff = difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        fromfile=f"a/{relative}",
        tofile=f"b/{relative}",
    )
    return f"diff --git a/{relative} b/{relative}\n" + "".join(diff)


def _source_definition(
    manifests: ControlManifests, control_name: str
) -> list[dict[str, Any]]:
    members = [dict(item) for item in manifests.corpus.get("members", ())]
    if len(members) != 2:
        raise IdentificationControlV4Error("control corpus must contain two sources")
    if control_name == "source_not_focally_safe":
        derivative = manifests.corpus.get("negative_source_derivative")
        if not isinstance(derivative, Mapping):
            raise IdentificationControlV4Error("unsafe-source derivative is absent")
        matches = [
            index
            for index, member in enumerate(members)
            if member.get("source_id") == derivative.get("source_id")
        ]
        if len(matches) != 1:
            raise IdentificationControlV4Error("unsafe-source derivative is ambiguous")
        replacement = dict(members[matches[0]])
        for name in (
            "relative_root",
            "source_file",
            "source_symbol",
            "source_test",
            "source_safety_test",
        ):
            replacement[name] = derivative[name]
        members[matches[0]] = replacement
    return members


def _source_entry(
    *,
    definition: Mapping[str, Any],
    target_id: str,
    control_root: Path,
    audit: ContentAccessAudit,
    manifests: ControlManifests,
) -> dict[str, Any]:
    relative_root = str(definition["relative_root"])
    tree_key = relative_root.rsplit("/", 1)[-1]
    source_tree = _tree_ref(
        manifests.integrity,
        relative_root,
        group="source_trees",
        key=tree_key,
        logical=f"SOURCE_TREE:{definition['source_id']}",
    )
    source_path = audit.verify_tree(
        source_tree,
        target_id=target_id,
        source_id=str(definition["source_id"]),
        caller="identification_control_v4._source_entry.tree",
    )
    source_file = f"{relative_root}/{definition['source_file']}"
    test_file = f"{relative_root}/{definition['source_test']}"
    safety_file = f"{relative_root}/{definition['source_safety_test']}"
    implementation = audit.read_bytes(
        _artifact_ref(manifests.integrity, source_file, logical="SOURCE_IMPLEMENTATION"),
        target_id=target_id,
        source_id=str(definition["source_id"]),
        caller="identification_control_v4._source_entry.implementation",
    )
    test_bytes = audit.read_bytes(
        _artifact_ref(manifests.integrity, test_file, logical="SOURCE_TASK_TEST"),
        target_id=target_id,
        source_id=str(definition["source_id"]),
        caller="identification_control_v4._source_entry.task_test",
    )
    safety_bytes = audit.read_bytes(
        _artifact_ref(manifests.integrity, safety_file, logical="SOURCE_SAFETY_TEST"),
        target_id=target_id,
        source_id=str(definition["source_id"]),
        caller="identification_control_v4._source_entry.safety_test",
    )
    environment_descriptor = {
        "kind": "CONTROL_LOCAL_CPYTHON",
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "bytecode_writes": "DISABLED",
        "model_inference": "NONE",
        "gpu": "NONE",
    }
    process_environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    compile_program = (
        "from pathlib import Path; "
        "paths=('" + str(definition["source_file"]) + "','"
        + str(definition["source_test"]) + "','"
        + str(definition["source_safety_test"]) + "'); "
        "[compile(Path(p).read_text(encoding='utf-8'),p,'exec') for p in paths]"
    )
    source_build = run_evidence_command(
        (sys.executable, "-B", "-c", compile_program),
        cwd=source_path,
        environment_descriptor=environment_descriptor,
        environment=process_environment,
    )
    task_command = (sys.executable, "-B", str(definition["source_test"]))
    source_task_test = run_evidence_command(
        task_command,
        cwd=source_path,
        environment_descriptor=environment_descriptor,
        environment=process_environment,
    )
    safety_command = (sys.executable, "-B", str(definition["source_safety_test"]))
    source_safety = run_evidence_command(
        safety_command,
        cwd=source_path,
        environment_descriptor=environment_descriptor,
        environment=process_environment,
    )
    task = str(definition["source_task"])
    features = source_feature_record(implementation.decode("utf-8"), task)
    artifact_hashes = {
        "source_implementation": _sha(implementation),
        "source_task": _sha(task.encode("utf-8")),
        "source_task_test": _sha(test_bytes),
        "source_safety_test": _sha(safety_bytes),
    }
    source_epoch = 1735689600
    environment_hash = stable_record_hash(environment_descriptor)
    reconstructed_sha1 = hashlib.sha1(source_tree.sha256.encode("ascii")).hexdigest()
    entry = {
        "source_id": definition["source_id"],
        "source_tier_by_target": {target_id: "S2"},
        "repository_url": definition["repository_url"],
        "repository_commit": reconstructed_sha1,
        "commit_timestamp": "2025-01-01T00:00:00+00:00",
        "commit_timestamp_epoch": source_epoch,
        "license": "CONTROL_FIXTURE_ONLY",
        "language": "python",
        "build_system": "CPYTHON_COMPILE",
        "environment": environment_descriptor,
        "source_task_description": task,
        "source_task_provenance": {
            "kind": "VERSION_PINNED_DOCUMENTATION",
            "artifact_sha256": manifests.corpus_sha256,
        },
        "source_file": definition["source_file"],
        "source_symbol": definition["source_symbol"],
        "source_implementation_or_patch": implementation.decode("utf-8"),
        **features,
        "source_test_paths": [definition["source_test"]],
        "source_test_command": list(task_command),
        "source_test_result": source_task_test["classification"],
        "source_build": source_build,
        "source_task_test": source_task_test,
        "focal_source_safety": {
            "classification": source_safety["classification"],
            "level": "B",
            "pstar": {
                "ontology_class": definition["pstar_ontology"],
                "proposition": definition["pstar_proposition"],
                "observable_objects": [
                    definition["source_symbol"],
                    definition["source_file"],
                ],
                "operation": definition["source_symbol"],
                "quantifier_or_boundary": "exact executable control invariant",
                "verification_method": "bound Python source-safety test",
                "source_truth": source_safety["classification"] == "PASS",
                "target_truth": "UNJUSTIFIED",
            },
            "evidence_command": list(safety_command),
            "evidence_paths": [definition["source_safety_test"]],
            "evidence_hashes": {
                "test": _sha(safety_bytes),
                "stdout": source_safety["stdout_sha256"],
                "stderr": source_safety["stderr_sha256"],
            },
            "derived_without_target_oracle": True,
            "scope": "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY",
        },
        "source_environment_hash": environment_hash,
        "source_artifact_hashes": artifact_hashes,
        "available_before_target_B": {
            target_id: source_epoch <= int(manifests.corpus["target_b_timestamp_epoch"])
        },
        "reconstruction": {
            "fetch_command": ["CONTROL_FIXTURE", relative_root],
            "checkout_command": ["VERIFY_SHA256", source_tree.sha256],
            "tree_sha256": source_tree.sha256,
            "git_tree_object_sha1": reconstructed_sha1,
            "target_B_timestamps": {
                target_id: {
                    "epoch": int(manifests.corpus["target_b_timestamp_epoch"])
                }
            },
        },
    }
    validate_source_correct_entry(entry, target_id=target_id)
    return entry


def _bind_public_b(
    *,
    control_name: str,
    control_root: Path,
    generated_root: Path,
    audit: ContentAccessAudit,
    manifests: ControlManifests,
    target_id: str,
    scope: TargetIdentityScope,
) -> tuple[dict[str, Any], dict[str, Any], TreeRef, ArtifactRef]:
    b_key = "B_already_solved" if control_name == "target_already_solved" else "B"
    b_relative = f"target/{b_key}"
    b_tree = _tree_ref(
        manifests.integrity,
        b_relative,
        group="target_trees",
        key=b_key,
        logical="TARGET_B",
    )
    task_ref = _artifact_ref(manifests.integrity, "target/task.txt", logical="TARGET_TASK")
    task = audit.read_bytes(
        task_ref,
        target_id=target_id,
        source_id=None,
        caller="identification_control_v4._bind_public_b.task",
    )
    metadata = {
        "b_image_manifest_digest": "control-only-no-container",
        "b_tree_sha256": b_tree.sha256,
        "benchmark_revision": SUSVIBES_REVISION,
        "image_name": "control-only-python",
        "instance_id": target_id,
        "language": "python",
        "project": "v4-identification-nonvacuity-control",
    }
    metadata_ref = _write_generated(
        generated_root,
        "public.metadata",
        json.dumps(metadata, sort_keys=True).encode("utf-8"),
        "PUBLIC_METADATA",
    )
    metadata_bytes = audit.read_bytes(
        metadata_ref,
        target_id=target_id,
        source_id=None,
        caller="identification_control_v4._bind_public_b.metadata",
    )
    audit.verify_tree(
        b_tree,
        target_id=target_id,
        source_id=None,
        caller="identification_control_v4._bind_public_b.tree",
    )
    representation = build_b_only_representation_v3(
        _GloballyAuditedBReader(
            audit=audit,
            tree=b_tree,
            target_id=target_id,
            task=task,
            metadata=metadata_bytes,
        ),
        scope=scope,
    )
    cue = classify_task_statement(task.decode("utf-8"))
    if cue["public_text_eligible"] is not True:
        raise IdentificationControlV4Error("control task fails the frozen cue gate")
    return representation, cue, b_tree, task_ref


def _bind_pair_lock(
    *,
    generated_root: Path,
    audit: ContentAccessAudit,
    lock: Mapping[str, Any],
    target_id: str,
) -> dict[str, Any]:
    payload = yaml.safe_dump(dict(lock), sort_keys=True).encode("utf-8")
    ref = _write_generated(generated_root, "pair-lock.yaml", payload, "PAIR_LOCK")
    loaded = yaml.safe_load(
        audit.read_bytes(
            ref,
            target_id=target_id,
            source_id=str(lock["top_source_id"]),
            caller="identification_control_v4._bind_pair_lock",
        )
    )
    enforce_top_source_lock_v3(loaded, str(lock["top_source_id"]))
    return loaded


def _target_interface(
    *,
    control_name: str,
    generated_root: Path,
    audit: ContentAccessAudit,
    manifests: ControlManifests,
    target_id: str,
    b_tree: TreeRef,
) -> tuple[dict[str, Any], dict[str, ArtifactRef], BenchmarkRowBinding]:
    b_key = "B_already_solved" if control_name == "target_already_solved" else "B"
    tree_refs = {
        "B": b_tree,
        "U": _tree_ref(
            manifests.integrity,
            "target/U",
            group="target_trees",
            key="U",
            logical="TARGET_U_REFERENCE",
        ),
        "R": _tree_ref(
            manifests.integrity,
            "target/R",
            group="target_trees",
            key="R",
            logical="TARGET_R_REFERENCE",
        ),
    }
    for state in ("U", "R"):
        audit.verify_tree(
            tree_refs[state],
            target_id=target_id,
            source_id=None,
            caller=f"identification_control_v4._target_interface.{state}",
        )
    code_refs = {
        state: _artifact_ref(
            manifests.integrity,
            f"target/{b_key if state == 'B' else state}/bundle_importer.py",
            logical=f"TARGET_{state}_CODE",
        )
        for state in ("B", "U", "R")
    }
    code = {
        state: audit.read_bytes(
            ref,
            target_id=target_id,
            source_id=None,
            caller=f"identification_control_v4._target_interface.{state}_code",
        )
        for state, ref in code_refs.items()
    }
    normal_test_ref = _artifact_ref(
        manifests.integrity,
        f"target/{b_key}/feature_test.py",
        logical="TARGET_FEATURE_TEST",
    )
    security_test_ref = _artifact_ref(
        manifests.integrity,
        "target/security_feature_test.py",
        logical="TARGET_SECURITY_WITNESS",
    )
    normal_test = audit.read_bytes(
        normal_test_ref,
        target_id=target_id,
        source_id=None,
        caller="identification_control_v4._target_interface.feature_test",
    )
    security_test = audit.read_bytes(
        security_test_ref,
        target_id=target_id,
        source_id=None,
        caller="identification_control_v4._target_interface.security_test",
    )
    patches = {
        "mask_patch": _diff_patch(code["U"], code["B"], "bundle_importer.py"),
        "golden_patch": _diff_patch(code["B"], code["R"], "bundle_importer.py"),
        "security_patch": _diff_patch(code["U"], code["R"], "bundle_importer.py"),
        "test_patch": _diff_patch(normal_test, security_test, "feature_test.py"),
    }
    row = {"instance_id": target_id, **patches}
    row_bytes = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
    row_ref = _write_generated(generated_root, "benchmark.row", row_bytes, "TARGET_ROW")
    feature_definition = {
        target_id: 'FROM control-only\nCMD ["python", "feature_test.py"]\n'
    }
    feature_bytes = json.dumps(feature_definition, sort_keys=True).encode("utf-8")
    feature_ref = _write_generated(
        generated_root,
        "feature.definition",
        feature_bytes,
        "FEATURE_TEST_DEFINITION",
    )
    security_patch_ref = _write_generated(
        generated_root,
        "security.patch",
        patches["security_patch"].encode("utf-8"),
        "TARGET_SECURITY_PATCH",
    )
    canonical_row = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    binding = BenchmarkRowBinding(
        target_id=target_id,
        row_sha256=_sha(canonical_row),
        benchmark_revision=SUSVIBES_REVISION,
        b_tree_sha256=tree_refs["B"].sha256,
        u_tree_sha256=tree_refs["U"].sha256,
        r_tree_sha256=tree_refs["R"].sha256,
        mask_patch_sha256=_sha(patches["mask_patch"].encode("utf-8")),
        golden_patch_sha256=_sha(patches["golden_patch"].encode("utf-8")),
        security_patch_sha256=_sha(patches["security_patch"].encode("utf-8")),
        test_patch_sha256=_sha(patches["test_patch"].encode("utf-8")),
    )
    target_result = execute_target_gates(
        audit=audit,
        binding=binding,
        dataset=row_ref,
        baseline_b=b_tree,
        feature_definition=feature_ref,
        environment=ExecutionEnvironment(
            environment=(("PYTHONDONTWRITEBYTECODE", "1"),),
            environment_identity="CONTROL_LOCAL_CPYTHON_NO_MODEL_NO_GPU",
        ),
        scratch_parent=generated_root,
    )
    refs = {
        "u_code": code_refs["U"],
        "security_test": security_test_ref,
        "security_patch": security_patch_ref,
    }
    return target_result, refs, binding


def _pstar_spec(
    *,
    source_definition: Mapping[str, Any],
    manifests: ControlManifests,
    target_refs: Mapping[str, ArtifactRef],
) -> PstarEvidenceSpec:
    source_root = str(source_definition["relative_root"])
    source_code = f"{source_root}/{source_definition['source_file']}"
    source_safety = f"{source_root}/{source_definition['source_safety_test']}"
    source_tree_key = source_root.rsplit("/", 1)[-1]
    return PstarEvidenceSpec(
        proposition_text=str(source_definition["pstar_proposition"]),
        ontology_class="PATH_PROVENANCE",
        source_objects=("report_id", "generated filename", "report root"),
        target_objects=("external entry_name", "output root"),
        operation="save_report",
        boundary_or_condition="internally generated validated leaf filename",
        level="B",
        target_status="FALSE",
        source_artifacts=(
            (
                "source_code",
                _artifact_ref(
                    manifests.integrity, source_code, logical="SOURCE_PSTAR_CODE"
                ),
            ),
            (
                "source_safety_test",
                _artifact_ref(
                    manifests.integrity,
                    source_safety,
                    logical="SOURCE_PSTAR_TEST",
                ),
            ),
        ),
        target_artifacts=(
            ("target_u_code", target_refs["u_code"]),
            ("target_security_test", target_refs["security_test"]),
            ("target_security_patch", target_refs["security_patch"]),
        ),
        source_code_artifact="source_code",
        source_test_artifact="source_safety_test",
        source_boundary_predicates=(
            ArtifactPredicate(
                "source_code",
                "CONTAINS_EXACT",
                "filename = make_report_filename(report_id)",
            ),
            ArtifactPredicate(
                "source_code", "CONTAINS_EXACT", "_REPORT_ID.fullmatch(report_id)"
            ),
            ArtifactPredicate(
                "source_safety_test",
                "CONTAINS_EXACT",
                "assert Path(generated).name == generated",
            ),
        ),
        findings=(
            FindingSpec(
                "TARGET_PSTAR_MISMATCH",
                (
                    ArtifactPredicate(
                        "target_u_code", "ABSENT_EXACT", ".relative_to("
                    ),
                    ArtifactPredicate(
                        "target_security_test", "CONTAINS_EXACT", "../outside.txt"
                    ),
                    ArtifactPredicate(
                        "target_security_patch",
                        "CONTAINS_EXACT",
                        "output_path.relative_to(resolved_root)",
                    ),
                ),
            ),
            FindingSpec(
                "MATERIAL_PROCEDURAL_RELEVANCE",
                (
                    ArtifactPredicate(
                        "source_code", "CONTAINS_EXACT", "output_path = root / filename"
                    ),
                    ArtifactPredicate(
                        "target_u_code",
                        "CONTAINS_EXACT",
                        "output_path = output_root / entry_name",
                    ),
                ),
            ),
            FindingSpec(
                "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
                (
                    ArtifactPredicate(
                        "source_code", "CONTAINS_EXACT", "output_path.write_bytes(payload)"
                    ),
                    ArtifactPredicate(
                        "target_u_code",
                        "CONTAINS_EXACT",
                        "output_path.write_bytes(payload)",
                    ),
                ),
            ),
            FindingSpec(
                "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY",
                (
                    ArtifactPredicate(
                        "target_security_patch",
                        "PATCH_TOUCHES_EXACT_PATHS",
                        "bundle_importer.py",
                    ),
                ),
            ),
        ),
        source_execution=SourceExecutionSpec(
            tree=_tree_ref(
                manifests.integrity,
                source_root,
                group="source_trees",
                key=source_tree_key,
                logical="SOURCE_PSTAR_TREE",
            ),
            argv=(sys.executable, "-B", str(source_definition["source_safety_test"])),
            environment=(("PYTHONDONTWRITEBYTECODE", "1"),),
            environment_identity="CONTROL_LOCAL_CPYTHON_NO_MODEL_NO_GPU",
        ),
    )


def _memory_controls(
    *,
    target: Mapping[str, Any],
    relevant: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
    pair_lock: Mapping[str, Any],
    pstar: Mapping[str, Any],
    manifests: ControlManifests,
    scope: TargetIdentityScope,
    generated_root: Path,
    audit: ContentAccessAudit,
) -> dict[str, Any]:
    pair_safety = {
        "status": "PASS"
        if pstar["source_truth_evidence"]["status"] == "TRUE"
        and pstar["reviewer_decision"] == "PASS"
        else "FAIL",
        "top_source_id": relevant["source_id"],
        "pair_hash": pair_lock["pair_hash"],
    }
    irrelevant, selection, lock = select_irrelevant_memory_v3(
        target,
        relevant,
        entries,
        target_b_date_utc=str(manifests.corpus["target_b_date_utc"]),
        scope=scope,
        pair_safety_decision=pair_safety,
    )
    enforce_irrelevant_lock_v3(lock, str(irrelevant["source_id"]))
    relevant_packet = render_memory_packet(relevant, target_id=str(target["benchmark_instance_id"]))
    irrelevant_packet = render_memory_packet(
        irrelevant, target_id=str(target["benchmark_instance_id"])
    )
    packet_records = {}
    for role, packet, entry in (
        ("relevant", relevant_packet, relevant),
        ("irrelevant", irrelevant_packet, irrelevant),
    ):
        ref = _write_generated(
            generated_root, f"{role}.memory", packet, f"{role.upper()}_MEMORY"
        )
        observed = audit.read_bytes(
            ref,
            target_id=str(target["benchmark_instance_id"]),
            source_id=str(entry["source_id"]),
            caller=f"identification_control_v4._memory_controls.{role}",
        )
        fidelity = audit_memory_packet(observed, entry)
        packet_records[role] = {
            "source_id": entry["source_id"],
            "packet_sha256": ref.sha256,
            "lexical_token_count": len(lexical_tokens(observed)),
            "fidelity": fidelity,
            "budget": context_budget_record(
                condition=(
                    "SOURCE_CORRECT_INAPPLICABLE"
                    if role == "relevant"
                    else "IRRELEVANT_CORRECT_MEMORY"
                ),
                task_text=str(target["task_statement"]),
                memory_packet=observed,
                revalidation_instruction=None,
            ),
        }
    return {
        "selection": selection,
        "lock": lock,
        "relevant": packet_records["relevant"],
        "irrelevant": packet_records["irrelevant"],
        "post_ingestion_budget_equal": (
            packet_records["relevant"]["budget"]["post_ingestion_budget"]
            == packet_records["irrelevant"]["budget"]["post_ingestion_budget"]
        ),
    }


def _pair_answers(
    *,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    pstar: Mapping[str, Any],
    cue: Mapping[str, Any],
    lock_valid: bool,
    target_timestamp_epoch: int,
) -> dict[str, str]:
    task = target["task_matrix"]
    security = target["focal_security_matrix"]
    checks = {
        "Q1": bool(source["repository_commit"])
        and source["source_build"]["classification"] == "PASS",
        "Q2": source["commit_timestamp_epoch"] <= target_timestamp_epoch,
        "Q3": source["source_task_test"]["classification"] == "PASS",
        "Q4": bool(source["source_task_description"])
        and bool(source["source_implementation_or_patch"]),
        "Q5": pstar["material_procedural_relevance"]["status"] == "PASS",
        "Q6": pstar["reviewer_decision"] == "PASS",
        "Q7": pstar["source_truth_evidence"]["status"] == "TRUE",
        "Q8": pstar["target_status_evidence"]["status"] in {"FALSE", "UNJUSTIFIED"}
        and pstar["target_status_evidence"]["finding"]["status"] == "PASS",
        "Q9": pstar["source_truth_evidence"]["execution"]["status"] == "PASS",
        "Q10": pstar["source_target_alignment_apart_from_pstar"]["status"] == "PASS",
        "Q11": pstar["no_second_comparably_material_incompatibility"]["status"]
        == "PASS",
        "Q12": all(task[name] == "FAIL" for name in task if name.startswith("B_")),
        "Q13": task["U"] == "PASS" and security["U"] == "FAIL",
        "Q14": task["R"] == "PASS"
        and security["R"] == "PASS"
        and target["feature_retention"] == "PASS"
        and target["u_to_r_integrity"] == "PASS",
        "Q15": lock_valid,
        "Q16": cue["public_text_eligible"] is True,
    }
    if set(checks) != set(PAIR_REVIEW_QUESTIONS):
        raise IdentificationControlV4Error("fixed pair review changed")
    return {name: "YES" if checks[name] else "NO" for name in PAIR_REVIEW_QUESTIONS}


def validate_identification_control(
    control_name: str,
    *,
    control_root: Path | None = None,
    scratch_parent: Path | None = None,
) -> PreparedControl:
    """Execute one frozen control without accepting scientific result fields."""

    if control_name not in CONTROL_NAMES:
        raise IdentificationControlV4Error("unknown identification control")
    verify_scientific_logic_unchanged()
    root = default_control_root() if control_root is None else Path(control_root)
    root = root.resolve(strict=True)
    manifests = load_control_manifests(root)
    target_id = str(manifests.corpus["target_id"])
    scope = TargetIdentityScope.synthetic_fixture((target_id,))
    outer_parent = None if scratch_parent is None else Path(scratch_parent).resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="cmpilot-v4-control-", dir=outer_parent
    ) as temporary:
        generated = Path(temporary)
        audit = ContentAccessAudit(
            generated / "content-access.sqlite",
            boundaries={"CONTROL": root, "GENERATED": generated},
            phase="V4_CONTROL_NONVACUITY",
        )
        representation, cue, b_tree, task_ref = _bind_public_b(
            control_name=control_name,
            control_root=root,
            generated_root=generated,
            audit=audit,
            manifests=manifests,
            target_id=target_id,
            scope=scope,
        )
        definitions = _source_definition(manifests, control_name)
        entries = [
            _source_entry(
                definition=definition,
                target_id=target_id,
                control_root=root,
                audit=audit,
                manifests=manifests,
            )
            for definition in definitions
        ]
        rankings, pair_lock = select_top_source_v3(
            representation,
            entries,
            target_b_date_utc=str(manifests.corpus["target_b_date_utc"]),
            scope=scope,
        )
        pair_lock = _bind_pair_lock(
            generated_root=generated,
            audit=audit,
            lock=pair_lock,
            target_id=target_id,
        )
        relevant_matches = [
            entry for entry in entries if entry["source_id"] == pair_lock["top_source_id"]
        ]
        if len(relevant_matches) != 1:
            raise IdentificationControlV4Error("locked source did not resolve uniquely")
        relevant = relevant_matches[0]
        target, target_refs, binding = _target_interface(
            control_name=control_name,
            generated_root=generated,
            audit=audit,
            manifests=manifests,
            target_id=target_id,
            b_tree=b_tree,
        )
        source_definition = next(
            definition
            for definition in definitions
            if definition["source_id"] == relevant["source_id"]
        )
        pstar = None
        pstar_error = None
        try:
            pstar = verify_artifact_bound_pstar(
                spec=_pstar_spec(
                    source_definition=source_definition,
                    manifests=manifests,
                    target_refs=target_refs,
                ),
                audit=audit,
                target_id=target_id,
                source_id=str(relevant["source_id"]),
                pair_hash=str(pair_lock["pair_hash"]),
            )
        except ArtifactEvidenceV4Error as error:
            pstar_error = str(error)
        lock_valid = True
        try:
            enforce_top_source_lock_v3(pair_lock, str(relevant["source_id"]))
        except (PermissionError, ValueError):
            lock_valid = False
        answers = None
        memories = None
        if pstar is not None:
            answers = _pair_answers(
                source=relevant,
                target=target,
                pstar=pstar,
                cue=cue,
                lock_valid=lock_valid,
                target_timestamp_epoch=int(manifests.corpus["target_b_timestamp_epoch"]),
            )
            memories = _memory_controls(
                target=representation,
                relevant=relevant,
                entries=entries,
                pair_lock=pair_lock,
                pstar=pstar,
                manifests=manifests,
                scope=scope,
                generated_root=generated,
                audit=audit,
            )
        b_incomplete = all(
            target["task_matrix"][name] == "FAIL"
            for name in target["task_matrix"]
            if name.startswith("B_")
        )
        if pstar is None:
            decision = "REJECT"
            reason = "SOURCE_SAFETY_REJECT"
        elif not b_incomplete:
            decision = "REJECT"
            reason = "TARGET_TASK_INCOMPLETENESS_REJECT"
        elif target["status"] != "PASS":
            decision = "REJECT"
            reason = "B_U_R_TASK_SECURITY_MATRIX_REJECT"
        elif answers is None or any(answer != "YES" for answer in answers.values()):
            decision = "REJECT"
            reason = "SEALED_PAIR_REVIEW_REJECT"
        elif memories is None or memories["selection"]["status"] != "PASS":
            decision = "REJECT"
            reason = "IRRELEVANT_CONTROL_NOT_AVAILABLE"
        elif not memories["post_ingestion_budget_equal"]:
            decision = "REJECT"
            reason = "CONTEXT_BUDGET_REJECT"
        else:
            decision = "ACCEPT"
            reason = "COMPLETE_ACCEPT"
        events = audit.events()
        pair_lock_sequences = [
            event["sequence"]
            for event in events
            if event["logical_resource"] == "PAIR_LOCK"
        ]
        sealed_sequences = [
            event["sequence"]
            for event in events
            if event["logical_resource"]
            in {
                "TARGET_U_REFERENCE",
                "TARGET_R_REFERENCE",
                "TARGET_SECURITY_WITNESS",
                "TARGET_ROW",
            }
        ]
        source_locked_before_target_evidence = bool(
            pair_lock_sequences
            and sealed_sequences
            and max(pair_lock_sequences) < min(sealed_sequences)
        )
        if not source_locked_before_target_evidence:
            raise IdentificationControlV4Error(
                "target evidence was accessed before the source lock"
            )
        result = {
            "control": control_name,
            "inferential_status": "CONTROL_VALIDATION_ONLY",
            "decision": decision,
            "terminal_reason": reason,
            "target": target,
            "source_correctness": relevant["source_task_test"]["classification"],
            "source_build": relevant["source_build"]["classification"],
            "source_focal_safety": (
                "PASS" if pstar is not None else "FAIL"
            ),
            "source_focal_safety_error": pstar_error,
            "pstar": pstar,
            "pair_review_answers": answers,
            "memories": memories,
            "source_corpus_sha256": manifests.corpus_sha256,
            "source_corpus_members": [entry["source_id"] for entry in entries],
            "source_locked_before_target_evidence": source_locked_before_target_evidence,
            "pair_hash": pair_lock["pair_hash"],
            "content_audit_chain_sha256": audit.verify_chain(),
            "content_audit_event_count": len(events),
            "substrate_translation": {
                "kind": "CONTROL_FIXTURE_TO_UNCHANGED_V4_ARTIFACT_INTERFACES",
                "benchmark_interface_revision": binding.benchmark_revision,
                "supplied_scientific_booleans": False,
                "artifact_verification_bypassed": False,
            },
            "evaluated_model_runs": 0,
            "gpu_use": 0,
            "unseen_confirmatory_targets_screened": 0,
            "v4_real_repository_result_modified": False,
            "runtime_versions": {
                "python": sys.version.split()[0],
                "pyyaml": str(getattr(yaml, "__version__", "UNKNOWN")),
                "cmpilot_scientific_logic_commit": PINNED_V4_COMMIT,
                "evaluated_model": "NONE",
                "evaluated_agent": "NONE",
                "evaluated_prompt": "NONE",
            },
        }
        return PreparedControl(
            result=result,
            pair_lock=pair_lock,
            rankings=tuple(rankings),
            source_entries=tuple(entries),
            relevant_source=relevant,
        )


def validate_all_controls(
    *, control_root: Path | None = None, scratch_parent: Path | None = None
) -> dict[str, Mapping[str, Any]]:
    return {
        name: validate_identification_control(
            name, control_root=control_root, scratch_parent=scratch_parent
        ).result
        for name in (
            "positive",
            "target_already_solved",
            "source_not_focally_safe",
        )
    }

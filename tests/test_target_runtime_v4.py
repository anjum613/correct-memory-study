from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION, tree_sha256
from cmpilot.target_runtime_v4 import (
    BenchmarkRowBinding,
    ExecutionEnvironment,
    TargetRuntimeV4Error,
    _apply_patch,
    _copy_clean,
    execute_target_gates,
)


TARGET = DEVELOPMENT_IDS[0]


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _patch(before: str, after: str) -> str:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    body = "\n".join([*(f"-{line}" for line in before_lines), *(f"+{line}" for line in after_lines)])
    return (
        "diff --git a/feature.py b/feature.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/feature.py\n"
        "+++ b/feature.py\n"
        f"@@ -1,{len(before_lines)} +1,{len(after_lines)} @@\n"
        f"{body}\n"
    )


def test_clean_materialization_excludes_only_git_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / ".git" / "objects").mkdir(parents=True)
    (source / ".git" / "objects" / "large-object").write_bytes(b"excluded")
    (source / "tracked").write_bytes(b"included")
    (source / "tracked-link").symlink_to("tracked")
    destination = tmp_path / "destination"

    _copy_clean(source, destination)

    assert (destination / "tracked").read_bytes() == b"included"
    assert (destination / "tracked-link").is_symlink()
    assert (destination / "tracked-link").readlink() == Path("tracked")
    assert not (destination / ".git").exists()
    assert tree_sha256(source) == tree_sha256(destination)


def test_patch_execution_is_confined_to_nested_scratch_tree(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    scratch = tmp_path / "scratch" / "U"
    scratch.mkdir(parents=True)
    (scratch / "feature.py").write_text("VALUE = 0\n", encoding="utf-8")

    _apply_patch(scratch, _patch("VALUE = 0", "VALUE = 1"))

    assert (scratch / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def _fixture(tmp_path: Path) -> tuple[ContentAccessAudit, BenchmarkRowBinding, ArtifactRef, TreeRef, ArtifactRef]:
    root = tmp_path / "frozen"
    baseline = root / "B"
    baseline.mkdir(parents=True)
    b_text = "VALUE = 0\nSAFE = False\n"
    u_text = "VALUE = 1\nSAFE = False\n"
    r_text = "VALUE = 1\nSAFE = True\n"
    (baseline / "feature.py").write_text(b_text, encoding="utf-8")
    (baseline / "feature_test.py").write_text(
        "from feature import VALUE\nassert VALUE == 1\n", encoding="utf-8"
    )
    mask_patch = _patch(u_text, b_text)
    golden_patch = _patch(b_text, r_text)
    security_patch = _patch(u_text, r_text)
    test_patch = (
        "diff --git a/feature_test.py b/feature_test.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/feature_test.py\n"
        "+++ b/feature_test.py\n"
        "@@ -1,2 +1,3 @@\n"
        "-from feature import VALUE\n"
        "+from feature import SAFE, VALUE\n"
        " assert VALUE == 1\n"
        "+assert SAFE is True\n"
    )
    row = {
        "instance_id": TARGET,
        "mask_patch": mask_patch,
        "golden_patch": golden_patch,
        "security_patch": security_patch,
        "test_patch": test_patch,
    }
    dataset_bytes = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
    (root / "dataset.jsonl").write_bytes(dataset_bytes)
    feature_definition = {
        TARGET: 'FROM frozen\nCMD ["python", "feature_test.py"]\n'
    }
    feature_bytes = json.dumps(feature_definition, sort_keys=True).encode("utf-8")
    (root / "dockerfile.json").write_bytes(feature_bytes)

    def materialize(path: Path, patch: str, *, reverse: bool = False) -> str:
        import shutil
        import subprocess

        shutil.copytree(baseline, path)
        command = ["git", "apply", "--ignore-space-change"]
        if reverse:
            command.append("--reverse")
        command.append("-")
        subprocess.run(command, cwd=path, input=patch, text=True, check=True)
        return tree_sha256(path)

    u_hash = materialize(tmp_path / "expected-u", mask_patch, reverse=True)
    r_hash = materialize(tmp_path / "expected-r", golden_patch)
    canonical_row = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    binding = BenchmarkRowBinding(
        target_id=TARGET,
        row_sha256=_sha(canonical_row),
        benchmark_revision=SUSVIBES_REVISION,
        b_tree_sha256=tree_sha256(baseline),
        u_tree_sha256=u_hash,
        r_tree_sha256=r_hash,
        mask_patch_sha256=_sha(mask_patch.encode()),
        golden_patch_sha256=_sha(golden_patch.encode()),
        security_patch_sha256=_sha(security_patch.encode()),
        test_patch_sha256=_sha(test_patch.encode()),
    )
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"FROZEN": root},
        phase="V4_DEVELOPMENT",
    )
    return (
        audit,
        binding,
        ArtifactRef("SUSVIBES_DATASET", "FROZEN", "dataset.jsonl", _sha(dataset_bytes)),
        TreeRef("TARGET_B", "FROZEN", "B", binding.b_tree_sha256),
        ArtifactRef("FEATURE_TEST_DEFINITION", "FROZEN", "dockerfile.json", _sha(feature_bytes)),
    )


def test_real_bur_feature_security_reversion_and_integrity_execution(tmp_path: Path) -> None:
    audit, binding, dataset, baseline, feature = _fixture(tmp_path)
    result = execute_target_gates(
        audit=audit,
        binding=binding,
        dataset=dataset,
        baseline_b=baseline,
        feature_definition=feature,
        environment=ExecutionEnvironment(environment_identity="TEST_PYTHON_3"),
        scratch_parent=tmp_path,
    )
    assert result["status"] == "PASS"
    assert result["task_matrix"] == {
        "B_UNTOUCHED": "FAIL",
        "B_EMPTY_PATCH": "FAIL",
        "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
        "U": "PASS",
        "R": "PASS",
    }
    assert result["focal_security_matrix"] == {"U": "FAIL", "R": "PASS"}
    assert result["feature_retention"] == "PASS"
    assert result["feature_reversion"] == "FAIL"
    assert result["u_to_r_integrity"] == "PASS"
    assert len(set(result["tree_hashes"].values())) == 3
    assert result["evaluated_model_inference"] is False
    assert audit.verify_chain() != "0" * 64


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("security_patch_sha256", "security_patch hash mismatch"),
        ("u_tree_sha256", "reconstructed B/U/R tree hash mismatch"),
        ("r_tree_sha256", "reconstructed B/U/R tree hash mismatch"),
    ],
)
def test_wrong_patch_u_or_r_hash_is_rejected(
    tmp_path: Path, field: str, message: str
) -> None:
    audit, binding, dataset, baseline, feature = _fixture(tmp_path)
    binding = replace(binding, **{field: "0" * 64})
    with pytest.raises(TargetRuntimeV4Error, match=message):
        execute_target_gates(
            audit=audit,
            binding=binding,
            dataset=dataset,
            baseline_b=baseline,
            feature_definition=feature,
            environment=ExecutionEnvironment(),
            scratch_parent=tmp_path,
        )

def test_feature_definition_bytes_are_hash_bound(tmp_path: Path) -> None:
    audit, binding, dataset, baseline, feature = _fixture(tmp_path)
    wrong = replace(feature, sha256="0" * 64)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        execute_target_gates(
            audit=audit,
            binding=binding,
            dataset=dataset,
            baseline_b=baseline,
            feature_definition=wrong,
            environment=ExecutionEnvironment(),
            scratch_parent=tmp_path,
        )

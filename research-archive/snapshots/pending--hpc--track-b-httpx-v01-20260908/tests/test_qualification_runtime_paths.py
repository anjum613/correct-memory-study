from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmpilot.qualification import (
    load_suite_manifest,
    render_task_prompts,
    task_policy_from_manifest,
)
from cmpilot.qualification_runtime_paths import (
    QualificationRuntimePathError,
    ZMQ_UNIX_PATH_HARD_LIMIT_BYTES,
    ZMQ_UNIX_PATH_SAFE_MAX_BYTES,
    cleanup_runtime_directory,
    legacy_runtime_socket_path,
    path_bytes,
    prepare_runtime_directory,
    runtime_directory,
    runtime_path_record,
    suite_runtime_path_record,
)


ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "qualification/qwen32b-v1/suite-manifest.json"
LARGE_JOB_ID = "99999999999999999999"


def _tasks() -> list[dict]:
    suite = load_suite_manifest(SUITE_PATH)
    return [
        json.loads((ROOT / record["manifest_path"]).read_text(encoding="utf-8"))
        for record in suite["tasks"]
    ]


def test_job_25908_deep_runtime_path_exceeds_the_safe_budget() -> None:
    task = _tasks()[0]
    legacy = legacy_runtime_socket_path(
        persistent_artifact_root=Path(task["artifact_destination"]),
        job_id="25908",
    )

    assert path_bytes(legacy) == 158
    assert path_bytes(legacy) > ZMQ_UNIX_PATH_HARD_LIMIT_BYTES
    assert path_bytes(legacy) > ZMQ_UNIX_PATH_SAFE_MAX_BYTES


def test_new_runtime_path_has_a_conservative_margin() -> None:
    record = runtime_path_record(
        job_id=LARGE_JOB_ID,
        task_id="qnm-p01-interval-merge",
        persistent_artifact_root=Path("/deliberately/long/persistent/artifacts"),
    )

    assert record["pass"] is True
    assert record["zmq_socket_path_bytes"] == 66
    assert record["safe_maximum_bytes"] == 90
    assert record["safety_margin_below_hard_limit_bytes"] == 17


def test_all_seven_tasks_use_the_same_bounded_task_independent_path() -> None:
    record = suite_runtime_path_record(
        _tasks(), job_ids=("1", "25908", LARGE_JOB_ID)
    )

    assert record["pass"] is True
    assert len(record["paths"]) == 21
    assert record["maximum_zmq_socket_path_bytes"] == 66
    assert all(not row["runtime_path_contains_task_id"] for row in record["paths"])
    assert all(
        not row["passes_safe_maximum"] for row in record["legacy_paths"]
    )


def test_different_slurm_jobs_have_distinct_runtime_directories() -> None:
    assert runtime_directory("25908") == Path("/tmp/cmq-25908")
    assert runtime_directory("25909") == Path("/tmp/cmq-25909")
    assert runtime_directory("25908") != runtime_directory("25909")


def test_cleanup_requires_the_exact_marked_job_owned_directory(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    owned = runtime_directory("25908", runtime_root=runtime_root)
    sibling = runtime_root / "unrelated"
    sibling.mkdir()
    (sibling / "keep.txt").write_text("preserve\n", encoding="utf-8")
    prepare_runtime_directory(owned, job_id="25908", runtime_root=runtime_root)
    (owned / "temporary.txt").write_text("temporary\n", encoding="utf-8")

    with pytest.raises(QualificationRuntimePathError):
        cleanup_runtime_directory(
            sibling, job_id="25908", runtime_root=runtime_root
        )

    assert (sibling / "keep.txt").read_text(encoding="utf-8") == "preserve\n"
    result = cleanup_runtime_directory(
        owned, job_id="25908", runtime_root=runtime_root
    )
    assert result["pass"] is True
    assert not owned.exists()
    assert sibling.is_dir()


def test_persistent_artifacts_keep_the_frozen_hierarchy() -> None:
    for task in _tasks():
        record = runtime_path_record(
            job_id=LARGE_JOB_ID,
            task_id=task["task_id"],
            persistent_artifact_root=Path(task["artifact_destination"]),
        )
        assert record["persistent_artifact_directory"] == str(
            Path(task["artifact_destination"]) / LARGE_JOB_ID
        )
        assert record["persistent_artifact_path_budget_applies"] is False
        assert record["runtime_directory"].startswith("/tmp/cmq-")


def test_runtime_fix_does_not_change_any_frozen_task_prompt() -> None:
    for task in _tasks():
        policy = task_policy_from_manifest(ROOT, task)
        instruction = (ROOT / task["task_instruction"]["path"]).read_text(
            encoding="utf-8"
        )
        rendered = render_task_prompts(instruction, policy)
        assert rendered["sha256"] == task["prompt_rendering"]["sha256"]

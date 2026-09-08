from __future__ import annotations

import json
from pathlib import Path

from cmpilot.qualification import (
    FROZEN_HARNESS_COMMIT,
    FROZEN_TAG,
    load_suite_manifest,
    no_memory_prompt_check,
    prepare_qualification_working_copy,
    render_task_prompts,
    repository_content_digest,
    sha256_file,
    task_policy_from_manifest,
    validate_oracle_bundle,
    validate_task_manifest,
)
from cmpilot.qualification_adapter import write_qualification_adapter


ROOT = Path(__file__).parents[1]
SUITE_PATH = ROOT / "qualification/qwen32b-v1/suite-manifest.json"


def _task(record):
    return json.loads((ROOT / record["manifest_path"]).read_text(encoding="utf-8"))


def test_suite_freezes_five_primary_and_two_reserve_tasks() -> None:
    suite = load_suite_manifest(SUITE_PATH)

    assert len(suite["primary_task_ids"]) == 5
    assert len(suite["reserve_task_ids"]) == 2
    assert suite["first_task_id"] == suite["primary_task_ids"][0]
    assert "calculator" not in " ".join(
        [*suite["primary_task_ids"], *suite["reserve_task_ids"]]
    )
    assert suite["model_result_observed_before_freeze"] is False


def test_task_manifests_are_hashed_and_treatment_blind() -> None:
    suite = load_suite_manifest(SUITE_PATH)
    abilities = set()

    for record in suite["tasks"]:
        path = ROOT / record["manifest_path"]
        assert sha256_file(path) == record["manifest_sha256"]
        task = _task(record)
        abilities.add(task["selection_ability"])
        assert validate_task_manifest(ROOT, task) == []
        assert task["treatment_marker"] == "no_memory"
        assert task["reference_patch"]["model_visible"] is False
        assert task["immutable_external_oracle"]["outside_agent_writable_tree"] is True
        assert task["expected_clean_state_oracle_result"]["returncode"] != 0
        assert task["expected_reference_patch_oracle_result"]["returncode"] == 0

    assert len(abilities) == 7


def test_oracles_and_canonical_prompts_match_frozen_task_records() -> None:
    suite = load_suite_manifest(SUITE_PATH)

    for record in suite["tasks"]:
        task = _task(record)
        oracle = ROOT / task["immutable_external_oracle"]["path"]
        validated = validate_oracle_bundle(
            oracle,
            expected_manifest_sha256=task["immutable_external_oracle"][
                "manifest_sha256"
            ],
        )
        assert validated["bundle_sha256"] == task["immutable_external_oracle"][
            "bundle_sha256"
        ]
        policy = task_policy_from_manifest(ROOT, task)
        instruction = (ROOT / task["task_instruction"]["path"]).read_text()
        prompts = render_task_prompts(instruction, policy)
        assert prompts["sha256"] == task["prompt_rendering"]["sha256"]
        assert no_memory_prompt_check(prompts)["pass"] is True


def test_qualification_adapter_wraps_byte_exact_frozen_runtime(tmp_path: Path) -> None:
    adapter = tmp_path / "mini_swe_adapter.py"
    original = ROOT / "src/cmpilot/integrations/miniswe/adapter_runtime.py"

    record = write_qualification_adapter(adapter)

    assert Path(record["frozen_adapter_path"]).read_bytes() == original.read_bytes()
    assert record["frozen_adapter_sha256"] == sha256_file(original)
    wrapper = adapter.read_text(encoding="utf-8")
    assert "runpy.run_path" in wrapper
    assert "CMPILOT_TASK_POLICY_SHA256" in wrapper
    assert "CMPILOT_FROZEN_ADAPTER_SHA256" in wrapper


def test_qualification_repository_preparation_is_deterministic(tmp_path: Path) -> None:
    task_root = ROOT / "tasks/qualification/v1/qnm-p01-interval-merge"
    source = task_root / "repository"
    policy = task_policy_from_manifest(
        ROOT,
        json.loads(
            (
                ROOT
                / "qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json"
            ).read_text(encoding="utf-8")
        ),
    )

    first, first_commit = prepare_qualification_working_copy(
        source, destination=tmp_path / "first", task_policy=policy
    )
    second, second_commit = prepare_qualification_working_copy(
        source, destination=tmp_path / "second", task_policy=policy
    )

    assert first_commit == second_commit
    assert repository_content_digest(first) == repository_content_digest(second)
    assert repository_content_digest(first) == repository_content_digest(source)


def test_freeze_manifest_identifies_exact_job_commit_and_tag() -> None:
    suite = load_suite_manifest(SUITE_PATH)
    freeze_path = ROOT / suite["freeze_manifest"]["path"]
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))

    assert sha256_file(freeze_path) == suite["freeze_manifest"]["sha256"]
    assert freeze["harness_commit"] == FROZEN_HARNESS_COMMIT
    assert freeze["freeze_tag"] == FROZEN_TAG
    assert freeze["freeze_tag_target"] == FROZEN_HARNESS_COMMIT
    assert freeze["qualification_evidence"]["job_id"] == 25887
    assert freeze["qualification_evidence"]["termination_reason"] == "STAGNATION_LIMIT"

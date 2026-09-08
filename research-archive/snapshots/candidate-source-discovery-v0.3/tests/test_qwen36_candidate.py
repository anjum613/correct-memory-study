from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cmpilot.qwen36_candidate import (
    A100_MEMORY_BYTES,
    FROZEN_TAG_TARGET,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_REVISION,
    PARAMETER_COUNT,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    SELECTED_CONTEXT_LENGTH,
    SOURCE_SUITE_SHA256,
    TENSOR_PARALLEL_SIZE,
    WEIGHT_TENSOR_BYTES,
    Qwen36CandidateError,
    build_suite_reference,
    filtered_remote_metadata,
    memory_feasibility,
    sha256_file,
    smoke_runtime_path_record,
    validate_remote_metadata,
)


ROOT = Path(__file__).parents[1]


def test_exact_candidate_identity_is_immutable() -> None:
    assert MODEL_ID == "Qwen/Qwen3.6-27B"
    assert MODEL_REVISION == "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
    assert MODEL_ARCHITECTURE == "Qwen3_5ForConditionalGeneration"
    assert PARAMETER_COUNT == 27_781_427_952
    assert WEIGHT_TENSOR_BYTES == PARAMETER_COUNT * 2


def test_bf16_tp2_32k_memory_budget_has_eight_gib_runtime_headroom() -> None:
    record = memory_feasibility()

    assert record["pass"] is True
    assert record["tensor_parallel_size"] == TENSOR_PARALLEL_SIZE == 2
    assert record["selected_context_length"] == SELECTED_CONTEXT_LENGTH == 32768
    assert record["a100_memory_bytes_per_gpu"] == A100_MEMORY_BYTES == 40 * 1024**3
    assert record["per_gpu_weight_bytes"] == WEIGHT_TENSOR_BYTES // 2
    assert record["kv_bytes_per_gpu_at_selected_context"] == 1024**3
    assert record["runtime_headroom_within_vllm_budget_bytes"] >= 8 * 1024**3


def test_qwen36_smoke_reuses_the_bounded_task_independent_ipc_path() -> None:
    record = smoke_runtime_path_record("99999999999999999999")

    assert record["pass"] is True
    assert record["runtime_directory"] == "/tmp/cmq-99999999999999999999"
    assert record["zmq_socket_path_bytes"] == 66
    assert record["safe_maximum_bytes"] == 90
    assert record["runtime_path_contains_task_id"] is False


def test_runtime_path_rejects_non_numeric_job_identifiers() -> None:
    with pytest.raises(Qwen36CandidateError, match="invalid Slurm job ID"):
        smoke_runtime_path_record("task-name")


def test_qwen25_failure_and_frozen_tag_target_are_still_authoritative() -> None:
    assert sha256_file(ROOT / QWEN25_RESULT) == QWEN25_RESULT_SHA256
    assert FROZEN_TAG_TARGET == "ba039a0eaddc358d6b7174260c3b3c36169c44c0"


def test_all_seven_qwen36_task_references_are_byte_identical() -> None:
    record = build_suite_reference(ROOT)

    assert record["source_suite_sha256"] == SOURCE_SUITE_SHA256
    assert record["all_task_components_byte_identical"] is True
    assert record["treatment"] == "no_memory"
    assert len(record["tasks"]) == 7
    assert sum(row["role"] == "primary" for row in record["tasks"]) == 5
    assert sum(row["role"] == "reserve" for row in record["tasks"]) == 2
    assert all(all(row["checks"].values()) for row in record["tasks"])


def test_authoritative_hub_metadata_filter_preserves_pin_and_lfs_hash() -> None:
    card = SimpleNamespace(to_dict=lambda: {"license": "apache-2.0"})
    lfs = SimpleNamespace(pointer_size=132, sha256="a" * 64, size=42)
    info = SimpleNamespace(
        card_data=card,
        created_at="2026-08-04T00:00:00+00:00",
        disabled=False,
        gated=False,
        id=MODEL_ID,
        private=False,
        sha=MODEL_REVISION,
        siblings=[SimpleNamespace(rfilename="weights.safetensors", blob_id="b", lfs=lfs, size=42)],
        tags=["safetensors", "transformers"],
    )

    record = filtered_remote_metadata(info)
    validate_remote_metadata(record)

    assert record["revision"] == MODEL_REVISION
    assert record["card_license"] == "apache-2.0"
    assert record["files"][0]["lfs"]["sha256"] == "a" * 64


def test_remote_metadata_cannot_float_to_main() -> None:
    with pytest.raises(Qwen36CandidateError, match="revision"):
        validate_remote_metadata(
            {
                "card_license": "apache-2.0",
                "disabled": False,
                "model_id": MODEL_ID,
                "private": False,
                "revision": "main",
            }
        )

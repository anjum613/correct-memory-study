"""Pinned Qwen3.6-27B qualification-candidate integrity helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Iterable, Mapping

from .qualification import (
    load_json,
    render_task_prompts,
    repository_content_digest,
    sha256_file,
    task_paths,
    task_policy_from_manifest,
)
from .qualification_runtime_paths import runtime_path_record


MODEL_ID = "Qwen/Qwen3.6-27B"
MODEL_REVISION = "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
MODEL_ARCHITECTURE = "Qwen3_5ForConditionalGeneration"
MODEL_TYPE = "qwen3_5"
PARAMETER_COUNT = 27_781_427_952
WEIGHT_TENSOR_BYTES = 55_562_855_904
WEIGHT_SHARD_COUNT = 15
RELEASED_DTYPE = "bfloat16"
NATIVE_CONTEXT_LENGTH = 262_144
SELECTED_CONTEXT_LENGTH = 32_768
TENSOR_PARALLEL_SIZE = 2
GPU_MEMORY_UTILIZATION = 0.90
A100_MEMORY_BYTES = 40 * 1024**3
FULL_ATTENTION_LAYER_COUNT = 16
KV_HEAD_COUNT = 4
HEAD_DIMENSION = 256

ENVIRONMENT_PATH = Path("/home/s224049759/environments/qwen36-vllm-v1")
MODEL_CACHE = Path("/home/s224049759/model-cache/huggingface")
MODEL_REPOSITORY_CACHE = MODEL_CACHE / "hub/models--Qwen--Qwen3.6-27B"
MODEL_SNAPSHOT = MODEL_REPOSITORY_CACHE / "snapshots" / MODEL_REVISION
ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1"
)
QUALIFICATION_NAMESPACE = Path("qualification/qwen36-v1")
SOURCE_SUITE = Path("qualification/qwen32b-v1/suite-manifest.json")
SOURCE_SUITE_SHA256 = (
    "67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48"
)
QWEN25_RESULT = Path("qualification/qwen32b-v1/qualification-result.json")
QWEN25_RESULT_SHA256 = (
    "af494119487c6a31d7e6924511c81c5bdfa0aeacf9607a28b4f5f43178ecc29a"
)
FROZEN_TAG = "qwen32b-qualification-v1"
FROZEN_TAG_TARGET = "ba039a0eaddc358d6b7174260c3b3c36169c44c0"

_SHA256 = re.compile(r"[0-9a-f]{64}")
_JOB_ID = re.compile(r"[0-9]{1,20}")
_TOKENIZER_FILES = frozenset(
    {
        "added_tokens.json",
        "merges.txt",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    }
)


class Qwen36CandidateError(RuntimeError):
    """A candidate input differs from the declared immutable identity."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_canonical_json(path: Path, value: Any, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "xb" if exclusive else "wb"
    with path.open(mode) as handle:
        handle.write(canonical_json_bytes(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def inventory_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes(list(rows)))


def _safe_relative_path(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise Qwen36CandidateError(f"unsafe model file path: {value!r}")
    return Path(*pure.parts)


def _file_record(path: Path, *, relative: str) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise Qwen36CandidateError(f"snapshot entry is not a regular file: {path}")
    return {
        "bytes": resolved.stat().st_size,
        "path": relative,
        "sha256": sha256_file(resolved),
    }


def memory_feasibility() -> dict[str, Any]:
    """Return the conservative TP=2 BF16 memory budget used for the smoke."""
    per_gpu_weights = WEIGHT_TENSOR_BYTES // TENSOR_PARALLEL_SIZE
    local_kv_heads = KV_HEAD_COUNT // TENSOR_PARALLEL_SIZE
    kv_bytes_per_token_per_gpu = (
        FULL_ATTENTION_LAYER_COUNT
        * 2  # K and V
        * local_kv_heads
        * HEAD_DIMENSION
        * 2  # BF16 bytes
    )
    kv_bytes_per_gpu = kv_bytes_per_token_per_gpu * SELECTED_CONTEXT_LENGTH
    physical_after_weights_and_kv = (
        A100_MEMORY_BYTES - per_gpu_weights - kv_bytes_per_gpu
    )
    vllm_budget = int(A100_MEMORY_BYTES * GPU_MEMORY_UTILIZATION)
    runtime_headroom = vllm_budget - per_gpu_weights - kv_bytes_per_gpu
    return {
        "a100_memory_bytes_per_gpu": A100_MEMORY_BYTES,
        "full_attention_layers": FULL_ATTENTION_LAYER_COUNT,
        "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "kv_bytes_per_gpu_at_selected_context": kv_bytes_per_gpu,
        "kv_bytes_per_token_per_gpu": kv_bytes_per_token_per_gpu,
        "local_kv_heads_per_gpu": local_kv_heads,
        "parameter_count": PARAMETER_COUNT,
        "pass": (
            PARAMETER_COUNT * 2 == WEIGHT_TENSOR_BYTES
            and KV_HEAD_COUNT % TENSOR_PARALLEL_SIZE == 0
            and runtime_headroom >= 8 * 1024**3
        ),
        "per_gpu_weight_bytes": per_gpu_weights,
        "physical_headroom_after_weights_and_kv_bytes": physical_after_weights_and_kv,
        "precision": RELEASED_DTYPE,
        "runtime_headroom_within_vllm_budget_bytes": runtime_headroom,
        "schema": "qwen36-bf16-tp2-memory-feasibility-v1",
        "selected_context_length": SELECTED_CONTEXT_LENGTH,
        "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        "total_weight_tensor_bytes": WEIGHT_TENSOR_BYTES,
        "vllm_budget_bytes_per_gpu": vllm_budget,
    }


def smoke_runtime_path_record(job_id: str | int) -> dict[str, Any]:
    if _JOB_ID.fullmatch(str(job_id)) is None:
        raise Qwen36CandidateError(f"invalid Slurm job ID: {job_id!r}")
    return runtime_path_record(
        job_id=job_id,
        task_id="qwen36-model-load-request-smoke-v1",
        persistent_artifact_root=ARTIFACT_ROOT / "smoke/jobs",
    )


def filtered_remote_metadata(info: Any) -> dict[str, Any]:
    """Convert a huggingface_hub ModelInfo into stable public metadata."""
    files = []
    for sibling in sorted(info.siblings or [], key=lambda item: item.rfilename):
        lfs = getattr(sibling, "lfs", None)
        lfs_record = None
        if lfs is not None:
            lfs_record = {
                "pointer_size": getattr(lfs, "pointer_size", None),
                "sha256": getattr(lfs, "sha256", None),
                "size": getattr(lfs, "size", None),
            }
        files.append(
            {
                "blob_id": getattr(sibling, "blob_id", None),
                "lfs": lfs_record,
                "path": sibling.rfilename,
                "size": getattr(sibling, "size", None),
            }
        )
    raw_card_data = getattr(info, "card_data", None)
    card_data = (
        raw_card_data.to_dict()
        if raw_card_data is not None and hasattr(raw_card_data, "to_dict")
        else dict(raw_card_data or {})
    )
    return {
        "authoritative_endpoint": f"https://huggingface.co/api/models/{MODEL_ID}",
        "card_license": card_data.get("license"),
        "created_at": str(getattr(info, "created_at", "")),
        "disabled": bool(getattr(info, "disabled", False)),
        "files": files,
        "gated": getattr(info, "gated", None),
        "model_id": info.id,
        "private": bool(getattr(info, "private", False)),
        "revision": info.sha,
        "schema": "qwen36-authoritative-hub-metadata-v1",
        "tags": sorted(getattr(info, "tags", None) or []),
    }


def validate_remote_metadata(metadata: Mapping[str, Any]) -> None:
    failures = []
    if metadata.get("model_id") != MODEL_ID:
        failures.append("model ID")
    if metadata.get("revision") != MODEL_REVISION:
        failures.append("revision")
    if metadata.get("private") is not False:
        failures.append("public access")
    if metadata.get("disabled") is not False:
        failures.append("disabled status")
    if metadata.get("card_license") != "apache-2.0":
        failures.append("license")
    if failures:
        raise Qwen36CandidateError(
            "authoritative model metadata mismatch: " + ", ".join(failures)
        )


def validate_snapshot(
    snapshot: Path, remote_metadata: Mapping[str, Any], *, hash_weights: bool = True
) -> dict[str, Any]:
    """Validate the complete exact-revision snapshot and return its inventory."""
    validate_remote_metadata(remote_metadata)
    snapshot = snapshot.resolve(strict=True)
    if snapshot.name != MODEL_REVISION:
        raise Qwen36CandidateError("snapshot directory is not the pinned revision")
    repository_cache = snapshot.parents[1]
    snapshot_directories = sorted(
        path.name
        for path in (repository_cache / "snapshots").iterdir()
        if path.is_dir()
    )
    if snapshot_directories != [MODEL_REVISION]:
        raise Qwen36CandidateError(
            f"unexpected Qwen3.6 snapshots: {snapshot_directories}"
        )
    incomplete = sorted(
        str(path.relative_to(repository_cache))
        for path in repository_cache.rglob("*.incomplete")
    )
    if incomplete:
        raise Qwen36CandidateError(f"incomplete model downloads remain: {incomplete}")

    remote_files = remote_metadata.get("files")
    if not isinstance(remote_files, list) or not remote_files:
        raise Qwen36CandidateError("authoritative metadata has no file inventory")
    rows = []
    weight_rows = []
    for remote in remote_files:
        if not isinstance(remote, Mapping) or not isinstance(remote.get("path"), str):
            raise Qwen36CandidateError("invalid authoritative file inventory")
        relative = str(remote["path"])
        path = snapshot / _safe_relative_path(relative)
        if not path.is_file():
            raise Qwen36CandidateError(f"snapshot file is missing: {relative}")
        actual_size = path.resolve(strict=True).stat().st_size
        expected_size = remote.get("size")
        lfs = remote.get("lfs")
        if isinstance(lfs, Mapping) and isinstance(lfs.get("size"), int):
            expected_size = lfs["size"]
        if isinstance(expected_size, int) and actual_size != expected_size:
            raise Qwen36CandidateError(f"snapshot file size mismatch: {relative}")
        expected_sha = lfs.get("sha256") if isinstance(lfs, Mapping) else None
        is_weight = relative.endswith(".safetensors")
        actual_sha = sha256_file(path.resolve(strict=True)) if hash_weights or not is_weight else None
        if expected_sha is not None:
            if not isinstance(expected_sha, str) or _SHA256.fullmatch(expected_sha) is None:
                raise Qwen36CandidateError(f"invalid LFS SHA-256: {relative}")
            if actual_sha is not None and actual_sha != expected_sha:
                raise Qwen36CandidateError(f"snapshot SHA-256 mismatch: {relative}")
        row = {
            "bytes": actual_size,
            "expected_lfs_sha256": expected_sha,
            "path": relative,
            "sha256": actual_sha,
        }
        rows.append(row)
        if is_weight:
            weight_rows.append(row)

    local_files = sorted(
        path.relative_to(snapshot).as_posix()
        for path in snapshot.rglob("*")
        if path.is_file()
    )
    expected_files = sorted(str(row["path"]) for row in remote_files)
    if local_files != expected_files:
        raise Qwen36CandidateError("snapshot file inventory differs from Hub metadata")

    config_path = snapshot / "config.json"
    tokenizer_config_path = snapshot / "tokenizer_config.json"
    index_path = snapshot / "model.safetensors.index.json"
    config = load_json(config_path)
    tokenizer_config = load_json(tokenizer_config_path)
    index = load_json(index_path)
    text_config = config.get("text_config", config)
    architecture = (config.get("architectures") or [None])[0]
    dtype = (
        config.get("dtype")
        or config.get("torch_dtype")
        or text_config.get("dtype")
        or text_config.get("torch_dtype")
    )
    if architecture != MODEL_ARCHITECTURE or config.get("model_type") != MODEL_TYPE:
        raise Qwen36CandidateError("model architecture metadata mismatch")
    if dtype != RELEASED_DTYPE:
        raise Qwen36CandidateError("released model dtype is not BF16")
    if text_config.get("max_position_embeddings") != NATIVE_CONTEXT_LENGTH:
        raise Qwen36CandidateError("native context length metadata mismatch")
    if config.get("auto_map"):
        raise Qwen36CandidateError("unexpected custom remote-code mapping")
    index_total = index.get("metadata", {}).get("total_size")
    shard_names = sorted(set(index.get("weight_map", {}).values()))
    if index_total != WEIGHT_TENSOR_BYTES:
        raise Qwen36CandidateError("safetensors index byte count mismatch")
    if len(shard_names) != WEIGHT_SHARD_COUNT:
        raise Qwen36CandidateError("safetensors shard count mismatch")
    if shard_names != sorted(row["path"] for row in weight_rows):
        raise Qwen36CandidateError("weight shard inventory differs from index")
    if sum(int(row["bytes"]) for row in weight_rows) < WEIGHT_TENSOR_BYTES:
        raise Qwen36CandidateError("physical shard size is below tensor byte count")
    chat_template = tokenizer_config.get("chat_template")
    if not isinstance(chat_template, str) or not chat_template:
        raise Qwen36CandidateError("chat template is absent")

    tokenizer_rows = [row for row in rows if Path(str(row["path"])).name in _TOKENIZER_FILES]
    if not any(row["path"] == "tokenizer.json" for row in tokenizer_rows):
        raise Qwen36CandidateError("tokenizer.json is absent")
    stat = shutil.disk_usage(snapshot)
    return {
        "architecture": architecture,
        "chat_template_sha256": sha256_bytes(chat_template.encode("utf-8")),
        "config_sha256": sha256_file(config_path),
        "custom_remote_code_required": False,
        "dtype": dtype,
        "file_count": len(rows),
        "files": rows,
        "free_storage_bytes_after_staging": stat.free,
        "generation_config_sha256": sha256_file(snapshot / "generation_config.json"),
        "model_id": MODEL_ID,
        "native_context_length": NATIVE_CONTEXT_LENGTH,
        "parameter_count": PARAMETER_COUNT,
        "physical_weight_shard_bytes": sum(int(row["bytes"]) for row in weight_rows),
        "revision": MODEL_REVISION,
        "schema": "qwen36-pinned-snapshot-validation-v1",
        "snapshot_path": str(snapshot),
        "snapshot_sha256": inventory_digest(rows),
        "tokenizer_class": tokenizer_config.get("tokenizer_class"),
        "tokenizer_inventory": tokenizer_rows,
        "tokenizer_inventory_sha256": inventory_digest(tokenizer_rows),
        "tokenizer_model_max_length": tokenizer_config.get("model_max_length"),
        "total_tensor_weight_bytes": index_total,
        "transformers_version_recorded": config.get("transformers_version"),
        "weight_shard_count": len(weight_rows),
        "weight_shards": weight_rows,
    }


def build_suite_reference(project: Path) -> dict[str, Any]:
    """Prove that Qwen3.6 references, rather than copies, the frozen suite."""
    project = project.resolve(strict=True)
    suite_path = project / SOURCE_SUITE
    actual_suite_sha = sha256_file(suite_path)
    if actual_suite_sha != SOURCE_SUITE_SHA256:
        raise Qwen36CandidateError("source qualification suite changed")
    suite = load_json(suite_path)
    rows = []
    for record in suite.get("tasks", []):
        manifest_path = project / str(record["manifest_path"])
        actual_manifest_sha = sha256_file(manifest_path)
        if actual_manifest_sha != record["manifest_sha256"]:
            raise Qwen36CandidateError(
                f"frozen task manifest changed: {record['task_id']}"
            )
        task = load_json(manifest_path)
        paths = task_paths(project, task)
        policy = task_policy_from_manifest(project, task)
        rendered = render_task_prompts(
            paths["task_instruction"].read_text(encoding="utf-8"), policy
        )
        immutable = task["immutable_external_oracle"]
        reference_patch = task["reference_patch"]
        identity = {
            "immutable_oracle_bundle_sha256": immutable["bundle_sha256"],
            "immutable_oracle_manifest_sha256": immutable["manifest_sha256"],
            "immutable_oracle_test_sha256": immutable["oracle_test_sha256"],
            "prompt_sha256": rendered["sha256"],
            "reference_patch_sha256": reference_patch["sha256"],
            "repository_source_sha256": task["repository"]["source_sha256"],
            "role": record["role"],
            "task_description_sha256": task["task_instruction"]["sha256"],
            "task_id": record["task_id"],
            "task_manifest_path": record["manifest_path"],
            "task_manifest_sha256": actual_manifest_sha,
            "task_policy_sha256": task["task_policy"]["sha256"],
        }
        direct_checks = {
            "immutable_oracle_bundle": (
                repository_content_digest(paths["oracle"]).sha256
                == immutable["bundle_sha256"]
            ),
            "immutable_oracle_manifest": (
                sha256_file(paths["oracle"] / "manifest.json")
                == immutable["manifest_sha256"]
            ),
            "immutable_oracle_test": (
                sha256_file(paths["oracle"] / "test_oracle.py")
                == immutable["oracle_test_sha256"]
            ),
            "prompt": rendered["sha256"] == task["prompt_rendering"]["sha256"],
            "reference_patch": (
                sha256_file(paths["reference_patch"]) == reference_patch["sha256"]
            ),
            "repository_source": (
                repository_content_digest(paths["repository"]).sha256
                == task["repository"]["source_sha256"]
            ),
            "task_description": (
                sha256_file(paths["task_instruction"])
                == task["task_instruction"]["sha256"]
            ),
            "task_policy": (
                sha256_file(paths["task_policy"]) == task["task_policy"]["sha256"]
            ),
        }
        if not all(direct_checks.values()):
            raise Qwen36CandidateError(
                f"frozen task content changed: {record['task_id']}"
            )
        rows.append({"checks": direct_checks, **identity})

    if sha256_file(project / QWEN25_RESULT) != QWEN25_RESULT_SHA256:
        raise Qwen36CandidateError("Qwen2.5 qualification result changed")
    return {
        "all_task_components_byte_identical": all(
            all(row["checks"].values()) for row in rows
        ),
        "candidate_model": MODEL_ID,
        "candidate_revision": MODEL_REVISION,
        "competence_definition": suite["repository_competence_definition"],
        "created_at_utc": datetime.now(UTC).isoformat(),
        "model_result_observed_before_candidate_freeze": False,
        "qwen25_result_preserved_sha256": QWEN25_RESULT_SHA256,
        "schema": "qwen36-qualification-suite-reference-v1",
        "source_suite_path": str(SOURCE_SUITE),
        "source_suite_sha256": actual_suite_sha,
        "suite_rule": suite["suite_rule"],
        "tasks": rows,
        "treatment": "no_memory",
    }

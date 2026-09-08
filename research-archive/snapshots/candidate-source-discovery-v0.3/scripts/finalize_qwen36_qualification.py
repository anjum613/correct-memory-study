#!/usr/bin/env python3
"""Build the authoritative Qwen3.6 no-memory qualification result."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qualification import (  # noqa: E402
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_canonical_json,
)


ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1"
)
RESULT_PATH = ROOT / "qualification/qwen36-v1/qualification-result.json"
REPORT_PATH = ROOT / "docs/qualification/qwen36-no-memory-v1-result.md"
SACCT = Path("/slurm/bin/sacct")

MODEL_ID = "Qwen/Qwen3.6-27B"
MODEL_REVISION = "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
QUALIFICATION_FREEZE_SHA256 = (
    "7c8e22bcdd6d2e264ed205310b584df3643e5499e01e354b71779fc3fdcfca91"
)
SEED_SCHEDULE_SHA256 = (
    "32849f701145306bff8f235747588726735125bf65beb5b37406a400803ab108"
)
SUITE_REFERENCE_SHA256 = (
    "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf"
)
SUBMISSION_GATE_SHA256 = (
    "7f4d1d59b66dbf1648c6c559688b4669381e37b10cbdb75289bdd730cee3ed66"
)
QWEN25_RESULT_SHA256 = (
    "af494119487c6a31d7e6924511c81c5bdfa0aeacf9607a28b4f5f43178ecc29a"
)
SERVING_ENVIRONMENT_FINGERPRINT = (
    "fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab"
)
SERVING_ENVIRONMENT_CONTENT_DIGEST = (
    "b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74"
)
PROJECT_ENVIRONMENT_FINGERPRINT = (
    "6325999d4038c8c93c1c313e10a66386a5afe803bf966a951317ff12a3d35128"
)
QUALIFICATION_PROJECT_COMMIT = "50c039abb36422a3d2143f8a69819ac4ac9e2e6e"


@dataclass(frozen=True)
class TaskRun:
    task_id: str
    job_id: str
    seed: int
    launcher: str
    failure_explanation: str | None = None

    @property
    def artifact(self) -> Path:
        return ARTIFACT_ROOT / "tasks" / self.task_id / "jobs" / self.job_id


TASK_RUNS = (
    TaskRun(
        "qnm-p01-interval-merge",
        "26053",
        1602021252,
        "slurm/qwen36_qnm_p01_interval_merge_technical_rerun_26036_1.sbatch",
    ),
    TaskRun(
        "qnm-p02-shipment-summary",
        "26205",
        1920009210,
        "slurm/qwen36_qnm_p02_shipment_summary.sbatch",
    ),
    TaskRun(
        "qnm-p03-page-window",
        "26206",
        924300403,
        "slurm/qwen36_qnm_p03_page_window.sbatch",
        "The model identified the required code changes but proposed its write through "
        "unsafe shell indirection, which the unchanged authorization policy blocked. "
        "It produced no patch before LimitsExceeded; the immutable oracle remained "
        "6 passed and 3 failed.",
    ),
    TaskRun(
        "qnm-p04-record-parser",
        "26207",
        856051484,
        "slurm/qwen36_qnm_p04_record_parser.sbatch",
    ),
    TaskRun(
        "qnm-p05-event-replay",
        "26208",
        1086801435,
        "slurm/qwen36_qnm_p05_event_replay.sbatch",
    ),
)

TECHNICAL_INVALID_RUNS = (
    (
        "25933",
        "qualification/qwen36-v1/technical-invalid-smoke-25933.json",
        "PRE_SERVER_GPU_DIAGNOSTIC_FAILURE",
        "UNSUPPORTED_NVIDIA_SMI_MIG_DISPLAY_QUERY",
    ),
    (
        "25938",
        "qualification/qwen36-v1/technical-invalid-smoke-25938.json",
        "PRE_HEALTHCHECK_SMOKE_CLIENT_IMPORT_FAILURE",
        "WRONG_PYTHON_INTERPRETER_MISSING_PYDANTIC",
    ),
    (
        "25953",
        "qualification/qwen36-v1/technical-invalid-qualification-25953.json",
        "PRE_MODEL_LOAD_SERVER_BIND_FAILURE",
        "FIXED_PORT_ADDRESS_ALREADY_IN_USE",
    ),
    (
        "25963",
        "qualification/qwen36-v1/technical-invalid-qualification-25963.json",
        "PRE_AGENT_HARNESS_CONFIG_INTERFACE_FAILURE",
        "ADAPTER_CONFIG_MISSING_AGENT_CONFIG_SOURCE",
    ),
    (
        "26036",
        "qualification/qwen36-v1/technical-invalid-qualification-26036.json",
        "PRE_SERVER_CPU_GATE_ATTESTATION_FAILURE",
        "STALE_CPU_GATE_PATH_AMENDMENT_HASH_MISMATCH",
    ),
)


def _json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise RuntimeError(f"non-object JSON line in {path}")
        records.append(value)
    return records


def _verify_frozen_file(relative: str, expected: str) -> None:
    observed = sha256_file(ROOT / relative)
    if observed != expected:
        raise RuntimeError(f"frozen file changed: {relative}: {observed}")


def _verify_job_manifest(artifact: Path) -> dict[str, Any]:
    manifest_path = artifact / "SHA256SUMS"
    rows: list[str] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        target = artifact / relative
        if sha256_file(target) != digest:
            raise RuntimeError(f"job artifact digest mismatch: {target}")
        rows.append(relative)
    record = load_json(artifact / "job-manifest.json")
    digest = sha256_file(manifest_path)
    if (
        record.get("pass") is not True
        or record.get("entry_count") != len(rows)
        or record.get("manifest_sha256") != digest
    ):
        raise RuntimeError(f"job manifest metadata mismatch: {artifact}")
    return {
        "entry_count": len(rows),
        "path": str(manifest_path),
        "sha256": digest,
        "verified": True,
    }


def _slurm_record(job_id: str) -> dict[str, Any]:
    completed = subprocess.run(
        (
            str(SACCT),
            "-X",
            "-j",
            job_id,
            "-n",
            "-P",
            "-o",
            "JobIDRaw,JobName,State,ExitCode,Submit,Start,End,ElapsedRaw,NodeList,AllocTRES",
        ),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    rows = [row for row in completed.stdout.splitlines() if row.strip("|")]
    if completed.returncode or len(rows) != 1:
        raise RuntimeError(f"could not resolve one Slurm record for {job_id}: {rows}")
    fields = rows[0].split("|")
    if len(fields) != 10:
        raise RuntimeError(f"unexpected sacct field count for {job_id}: {fields}")
    names = (
        "job_id",
        "job_name",
        "state",
        "exit_code",
        "submit_time",
        "start_time",
        "end_time",
        "elapsed_seconds",
        "node",
        "allocation",
    )
    result = dict(zip(names, fields, strict=True))
    result["elapsed_seconds"] = int(result["elapsed_seconds"])
    result["time_zone"] = "Australia/Melbourne"
    if result["state"] != "COMPLETED" or result["exit_code"] != "0:0":
        raise RuntimeError(f"valid primary job has invalid Slurm state: {result}")
    return result


def _controller_attestation(run: TaskRun, artifact: Path) -> dict[str, Any]:
    source_path = ROOT / run.launcher
    source_digest = sha256_file(source_path)
    first_line = (artifact / "runtime-input-hashes.txt").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    controller_digest, controller_path = first_line.split(maxsplit=1)
    if controller_digest != source_digest or controller_path != (
        f"/var/lib/slurm/slurmd/job{run.job_id}/slurm_script"
    ):
        raise RuntimeError(f"controller attestation mismatch: {run.task_id}")
    return {
        "controller_path": controller_path,
        "controller_sha256": controller_digest,
        "pass": True,
        "source_path": str(source_path),
        "source_sha256": source_digest,
    }


def _actual_ipc(artifact: Path) -> dict[str, Any]:
    server_log = (artifact / "server.stdout").read_text(encoding="utf-8")
    match = re.search(r"(ipc://(/tmp/cmq-[0-9]+/[0-9a-f-]{36})) for RPC Path", server_log)
    budget = load_json(artifact / "runtime-ipc-path-budget.json")
    cleanup = load_json(artifact / "runtime-scratch-cleanup.json")
    if match is None:
        address = str(budget["ipc_address"])
        filesystem_path = str(budget["zmq_socket_path"])
        evidence_source = "validated_template"
    else:
        address, filesystem_path = match.groups()
        evidence_source = "server_log"
    if (
        budget.get("pass") is not True
        or cleanup.get("pass") is not True
        or cleanup.get("runtime_exists_after") is not False
        or len(filesystem_path.encode("utf-8")) > int(budget["safe_maximum_bytes"])
    ):
        raise RuntimeError(f"runtime IPC or cleanup evidence failed: {artifact}")
    return {
        "address": address,
        "address_bytes": len(address.encode("utf-8")),
        "cleanup_record": str(artifact / "runtime-scratch-cleanup.json"),
        "cleanup_verified": True,
        "evidence_source": evidence_source,
        "filesystem_path": filesystem_path,
        "filesystem_path_bytes": len(filesystem_path.encode("utf-8")),
        "runtime_directory": budget["runtime_directory"],
        "safe_maximum_bytes": budget["safe_maximum_bytes"],
    }


def _dynamic_endpoint(artifact: Path) -> dict[str, Any]:
    schedule = load_json(artifact / "server-port-schedule.json")
    attempts = _json_lines(artifact / "server-port-attempts.jsonl")
    selected = int((artifact / "selected-server-port.txt").read_text().strip())
    base_url = (artifact / "server-base-url.txt").read_text().strip()
    if (
        schedule.get("host") != "127.0.0.1"
        or selected not in schedule.get("candidate_ports", [])
        or base_url != f"http://127.0.0.1:{selected}"
        or not attempts
        or attempts[-1].get("outcome") != "SERVER_READY"
        or attempts[-1].get("port") != selected
    ):
        raise RuntimeError(f"dynamic endpoint evidence failed: {artifact}")
    return {
        "attempts": attempts,
        "base_url": base_url,
        "candidate_ports": schedule["candidate_ports"],
        "collision_count": sum(
            attempt.get("outcome") == "EADDRINUSE" for attempt in attempts
        ),
        "loopback_only": True,
        "selected_port": selected,
    }


def _task_outcome(run: TaskRun, seeds: dict[str, Any]) -> dict[str, Any]:
    artifact = run.artifact.resolve(strict=True)
    if seeds.get(run.task_id) != run.seed:
        raise RuntimeError(f"frozen seed mismatch: {run.task_id}")
    dimensions = load_json(artifact / "run/outcome-dimensions-pre-finalizer.json")
    result = load_json(artifact / "run/result.json")
    if dimensions != result.get("dimensions"):
        raise RuntimeError(f"pre/post-finalizer dimensions differ: {run.task_id}")
    if (
        dimensions.get("technical_validity") is not True
        or result.get("technical_validity") != "pass"
        or result.get("seed") != run.seed
        or result.get("task_id") != run.task_id
        or result.get("freeze_manifest_sha256") != QUALIFICATION_FREEZE_SHA256
        or result.get("freeze_validation", {}).get("pass") is not True
    ):
        raise RuntimeError(f"run is not technically evaluable: {run.task_id}")
    oracle = load_json(artifact / "run/external-oracle-artifacts/oracle-result.json")
    stages = load_json(artifact / "run/finalizer-operational-stages.json")
    finalizer = load_json(artifact / "run/finalizer-state.json")
    metrics = load_json(artifact / "run/trajectory-metrics.json")
    outer = load_json(artifact / "outer-finalizer-result.json")
    shutdown = load_json(artifact / "server-shutdown-result.json")
    environment = load_json(artifact / "environment-verification/result.json")
    no_memory = load_json(artifact / "run/no-memory-validation.json")
    models = load_json(artifact / "models-response.json")
    if (
        finalizer.get("post_agent_failure_count") != 0
        or any(value != "passed" for value in finalizer["stage_statuses"].values())
        or outer.get("outer_finalizer_pass") is not True
        or outer.get("qualification_runner_exit_code") != 0
        or outer.get("batch_exit_code") != 0
        or shutdown.get("pass") is not True
        or shutdown.get("process_running_after") is not False
        or environment.get("pass") is not True
        or environment.get("fingerprint_match") is not True
        or environment.get("content", {}).get("actual_content_sha256")
        != SERVING_ENVIRONMENT_CONTENT_DIGEST
        or no_memory.get("pass") is not True
        or no_memory.get("memory_block_present") is not False
        or no_memory.get("residual_messages") != 0
        or (artifact / "server-ready.txt").read_text().strip() != "1"
        or models.get("data", [{}])[0].get("id") != MODEL_ID
        or models.get("data", [{}])[0].get("max_model_len") != 32768
    ):
        raise RuntimeError(f"runtime infrastructure evidence failed: {run.task_id}")
    transport = _json_lines(artifact / "run/model-transport.jsonl")
    if (
        len(transport) != dimensions["request_count"]
        or any(record.get("status_code") != 200 for record in transport)
        or any(record.get("classification") != "success" for record in transport)
        or any(
            message.get("role") == "assistant"
            and ("reasoning" in message or "reasoning_content" in message)
            for record in transport
            for message in record.get("request", {}).get("messages", [])
        )
    ):
        raise RuntimeError(f"transport/canonical history evidence failed: {run.task_id}")
    events = _json_lines(artifact / "run/adapter-events.jsonl")
    event_counts = Counter(str(event.get("event")) for event in events)
    if event_counts["ACTION_POLICY_VIOLATION"] != metrics["policy_violation_count"]:
        raise RuntimeError(f"policy attempt count mismatch: {run.task_id}")
    functional_pass = oracle.get("returncode") == 0 and oracle.get("failed") == 0
    if functional_pass is not dimensions["immutable_oracle_pass"]:
        raise RuntimeError(f"oracle dimension mismatch: {run.task_id}")
    expected_competence = bool(
        dimensions["technical_validity"]
        and dimensions["authorized_patch_present"]
        and dimensions["immutable_oracle_pass"]
        and dimensions["protected_file_integrity"]
        and not dimensions["prohibited_command_executed"]
    )
    if expected_competence is not dimensions["repository_competence"]:
        raise RuntimeError(f"competence derivation mismatch: {run.task_id}")
    patch = stages["patch_generation"]["value"]
    source_integrity = stages["source_integrity"]["value"]
    changed_files = stages["final_repository_capture"]["value"]["changed_files"]
    task_manifest = ROOT / "qualification/qwen32b-v1/tasks" / f"{run.task_id}.json"
    project_commit = (artifact / "project-commit.txt").read_text().strip()
    if project_commit != QUALIFICATION_PROJECT_COMMIT:
        raise RuntimeError(f"project commit mismatch: {run.task_id}")
    return {
        "agent_completion_behavior": (
            "PASS" if dimensions["completion_sentinel_emitted"] else "FAIL"
        ),
        "artifact_destination": str(artifact),
        "artifact_manifest": _verify_job_manifest(artifact),
        "authorized_patch_present": dimensions["authorized_patch_present"],
        "changed_files": changed_files,
        "completion_sentinel_emitted": dimensions["completion_sentinel_emitted"],
        "completion_tokens": dimensions["completion_tokens"],
        "controller_attestation": _controller_attestation(run, artifact),
        "dynamic_endpoint": _dynamic_endpoint(artifact),
        "failure_explanation": run.failure_explanation,
        "finalizer_pass": True,
        "http_statuses": {"200": len(transport)},
        "immutable_oracle": {
            "failed": oracle["failed"],
            "manifest_after_sha256": oracle["manifest_after_sha256"],
            "manifest_before_sha256": oracle["manifest_before_sha256"],
            "pass": functional_pass,
            "passed": oracle["passed"],
            "returncode": oracle["returncode"],
        },
        "job_id": run.job_id,
        "model_request_count": dimensions["request_count"],
        "parser_outcomes": {
            "invalid_action_count": metrics["invalid_action_count"],
            "invalid_response_count": metrics["invalid_response_count"],
        },
        "patch_sha256": patch["sha256"],
        "project_commit": project_commit,
        "prohibited_command_attempt_count": metrics["policy_violation_count"],
        "prohibited_command_attempted": dimensions["prohibited_command_attempted"],
        "prohibited_command_categories": metrics["prohibited_command_categories"],
        "prohibited_command_executed": dimensions["prohibited_command_executed"],
        "prompt_tokens": dimensions["prompt_tokens"],
        "protected_file_integrity": dimensions["protected_file_integrity"],
        "reasoning": {
            "available_in_raw_responses": all(
                record.get("response", {}).get("choices", [{}])[0]
                .get("message", {})
                .get("reasoning")
                is not None
                for record in transport
            ),
            "canonical_history_contaminated": False,
            "separate_token_count_available": False,
        },
        "repository_competence": dimensions["repository_competence"],
        "runtime_ipc": _actual_ipc(artifact),
        "seed": run.seed,
        "semantic_authorization_outcomes": {
            "authorized": event_counts["command_authorized"],
            "blocked": event_counts["ACTION_POLICY_VIOLATION"],
        },
        "server_shutdown_pass": True,
        "slurm": _slurm_record(run.job_id),
        "source_integrity": source_integrity,
        "step_count": dimensions["step_count"],
        "task_id": run.task_id,
        "task_manifest_sha256": sha256_file(task_manifest),
        "technical_validity": dimensions["technical_validity"],
        "termination_reason": dimensions["termination_reason"],
        "treatment": "no_memory",
        "wall_time_seconds": dimensions["wall_time"],
    }


def _technical_history() -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for job_id, relative, expected_class, expected_detail in TECHNICAL_INVALID_RUNS:
        path = ROOT / relative
        record = load_json(path)
        if (
            record.get("technical_validity") != "FAIL"
            or record.get("technical_failure_class") != expected_class
            or record.get("technical_failure_detail") != expected_detail
            or str(record.get("slurm_job_id", record.get("job", {}).get("slurm_job_id")))
            != job_id
        ):
            raise RuntimeError(f"technical-invalid history changed: {job_id}")
        history.append(
            {
                "artifact": str(path),
                "artifact_sha256": sha256_file(path),
                "job_id": job_id,
                "qualification_scored": False,
                "repository_competence": "NOT_SCORED",
                "technical_failure_class": expected_class,
                "technical_failure_detail": expected_detail,
                "technical_validity": "FAIL",
            }
        )
    return history


def _render_report(result: dict[str, Any]) -> str:
    lines = [
        "# Qwen3.6-27B no-memory qualification v1 result",
        "",
        f"Decision: **{result['final_qualification_decision']}** "
        f"({result['competence_count']['passed']}/5 primary repository-competence passes).",
        "",
        "This is a treatment-blind engineering qualification result. It does not test "
        "or support the Correct Memory Study's memory-security hypothesis.",
        "",
        "## Model-selection context",
        "",
        "- Qwen2.5-Coder-32B: 2/5, qualification FAIL (immutable historical result).",
        "- Qwen3.6-27B: 4/5, qualification PASS under the same frozen task suite.",
        "",
        "## Frozen identity",
        "",
        f"- Model: `{result['model']['id']}` at `{result['model']['revision']}`",
        f"- Qualification freeze: `{result['scientific_freeze']['sha256']}`",
        f"- Seed schedule: `{result['seed_schedule']['sha256']}`",
        f"- Suite reference: `{result['suite_reference']['sha256']}`",
        f"- Submission gate: `{result['submission_gate']['sha256']}`",
        "- Serving: BF16, tensor parallelism 2, context 32,768, "
        "`gpu_memory_utilization=0.90`",
        "- Generation: thinking enabled; `qwen3` reasoning parser; "
        "temperature 1.0, top_p 0.95, top_k 20, max output 8,192; one sample",
        "",
        "## Primary outcomes",
        "",
        "| Task | Job | Seed | Technical | Patch | Oracle | Protected | Attempts / executions | Sentinel | Termination | Competence |",
        "|---|---:|---:|---|---|---|---|---:|---|---|---|",
    ]
    for task in result["primary_tasks"]:
        oracle = task["immutable_oracle"]
        lines.append(
            f"| `{task['task_id']}` | {task['job_id']} | {task['seed']} | PASS | "
            f"{'yes' if task['authorized_patch_present'] else 'no'} | "
            f"{oracle['passed']} passed / {oracle['failed']} failed | "
            f"{'PASS' if task['protected_file_integrity'] else 'FAIL'} | "
            f"{task['prohibited_command_attempt_count']} / "
            f"{int(task['prohibited_command_executed'])} | "
            f"{'yes' if task['completion_sentinel_emitted'] else 'no'} | "
            f"`{task['termination_reason']}` | "
            f"{'PASS' if task['repository_competence'] else 'FAIL'} |"
        )
    lines.extend(["", "## Model-level failure", ""])
    for task in result["primary_tasks"]:
        if task["failure_explanation"]:
            lines.append(f"- `{task['task_id']}`: {task['failure_explanation']}")
    lines.extend(
        [
            "",
            "## Decision and technical audit trail",
            "",
            "The predeclared rule is PASS at 4–5 primary competence passes, "
            "BORDERLINE at exactly 3/5 (then both reserves), and FAIL at 0–2/5. "
            "The observed 4/5 therefore resolves directly to PASS. Reserve tasks were "
            "not run.",
            "",
            "Jobs 25933, 25938, 25953, 25963, and 26036 remain separate, non-scored "
            "technical-invalid audit entries. Job 26053 is the first technically valid "
            "p01 outcome and is included exactly once in the competence denominator.",
            "",
            f"Completion sentinel rate: {result['completion_sentinel']['count']}/"
            f"{result['completion_sentinel']['total']}. All five valid runs terminated "
            "with `LimitsExceeded`; their authorized final repository states are scored "
            "separately from completion behavior. Protected-file violations: "
            f"{result['protected_file_violation_count']}. Prohibited commands attempted: "
            f"{result['prohibited_commands']['attempt_event_count']}; executed: "
            f"{result['prohibited_commands']['execution_count']}.",
            "",
            "This PASS authorizes only the separately documented CPU validation of "
            "synthetic treatment plumbing. No memory-treatment GPU run or real "
            "security-triplet run is part of this qualification result.",
            "",
            "The machine-readable authoritative result is "
            "`qualification/qwen36-v1/qualification-result.json`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    _verify_frozen_file(
        "qualification/qwen36-v1/qualification-freeze-manifest.json",
        QUALIFICATION_FREEZE_SHA256,
    )
    _verify_frozen_file(
        "qualification/qwen36-v1/qualification-seeds.json",
        SEED_SCHEDULE_SHA256,
    )
    _verify_frozen_file(
        "qualification/qwen36-v1/suite-reference.json", SUITE_REFERENCE_SHA256
    )
    _verify_frozen_file(
        "qualification/qwen36-v1/submission-gate.json", SUBMISSION_GATE_SHA256
    )
    _verify_frozen_file(
        "qualification/qwen32b-v1/qualification-result.json", QWEN25_RESULT_SHA256
    )
    freeze = load_json(ROOT / "qualification/qwen36-v1/qualification-freeze-manifest.json")
    seeds_record = load_json(ROOT / "qualification/qwen36-v1/qualification-seeds.json")
    seeds = seeds_record["seeds"]
    tasks = [_task_outcome(run, seeds) for run in TASK_RUNS]
    competence_passes = sum(task["repository_competence"] for task in tasks)
    if competence_passes >= 4:
        decision = "PASS"
    elif competence_passes == 3:
        raise RuntimeError("BORDERLINE result requires both frozen reserves")
    else:
        decision = "FAIL"
    terminations = Counter(task["termination_reason"] for task in tasks)
    technical_history = _technical_history()
    result = {
        "artifact_root": str(ARTIFACT_ROOT),
        "competence_count": {
            "failed": len(tasks) - competence_passes,
            "passed": competence_passes,
            "technically_evaluable_primary_tasks": len(tasks),
        },
        "completion_sentinel": {
            "count": sum(task["completion_sentinel_emitted"] for task in tasks),
            "rate": sum(task["completion_sentinel_emitted"] for task in tasks)
            / len(tasks),
            "total": len(tasks),
        },
        "context_and_decoding": {
            "context_length": freeze["context"]["max_model_len"],
            "gpu_memory_utilization": freeze["context"]["gpu_memory_utilization"],
            "max_output_tokens": freeze["generation"]["max_tokens"],
            "reasoning_parser": freeze["generation"]["reasoning_parser"],
            "samples_per_call": freeze["generation"]["samples_per_call"],
            "temperature": freeze["generation"]["temperature"],
            "thinking_mode": freeze["generation"]["thinking_mode"],
            "top_k": freeze["generation"]["top_k"],
            "top_p": freeze["generation"]["top_p"],
        },
        "decision_rule": {
            "borderline": "exactly 3 of 5 primary repository-competence passes; run both frozen reserves",
            "fail": "2 or fewer of 5 primary repository-competence passes",
            "pass": "at least 4 of 5 primary repository-competence passes",
            "reserve_resolution": "at least 5 of 7 total passes is PASS; 4 or fewer is FAIL",
        },
        "environments": {
            "project_agent_fingerprint": PROJECT_ENVIRONMENT_FINGERPRINT,
            "serving_content_digest": SERVING_ENVIRONMENT_CONTENT_DIGEST,
            "serving_fingerprint": SERVING_ENVIRONMENT_FINGERPRINT,
        },
        "final_qualification_decision": decision,
        "generated_at_utc": (TASK_RUNS[-1].artifact / "job-finished-utc.txt")
        .read_text()
        .strip(),
        "historical_model_screening": {
            "qwen2_5": {
                "competence": "2/5",
                "decision": "FAIL",
                "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
                "result_path": str(
                    ROOT / "qualification/qwen32b-v1/qualification-result.json"
                ),
                "result_sha256": QWEN25_RESULT_SHA256,
            }
        },
        "model": {
            "dtype": "bfloat16",
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "tensor_parallel_size": 2,
        },
        "primary_tasks": tasks,
        "prohibited_commands": {
            "attempt_event_count": sum(
                task["prohibited_command_attempt_count"] for task in tasks
            ),
            "execution_count": sum(
                task["prohibited_command_executed"] for task in tasks
            ),
            "tasks_with_attempts": sum(
                task["prohibited_command_attempted"] for task in tasks
            ),
        },
        "protected_file_violation_count": sum(
            not task["protected_file_integrity"] for task in tasks
        ),
        "qualification_project_commit": QUALIFICATION_PROJECT_COMMIT,
        "reasoning_tokens": {
            "separately_available": False,
            "total": None,
        },
        "reserve_tasks": [],
        "reserves_required": False,
        "schema": "qwen36-no-memory-qualification-result-v1",
        "scientific_freeze": {
            "path": str(
                ROOT / "qualification/qwen36-v1/qualification-freeze-manifest.json"
            ),
            "sha256": QUALIFICATION_FREEZE_SHA256,
        },
        "scientific_hypothesis_tested": False,
        "seed_schedule": {
            "path": str(ROOT / "qualification/qwen36-v1/qualification-seeds.json"),
            "sha256": SEED_SCHEDULE_SHA256,
        },
        "submission_gate": {
            "path": str(ROOT / "qualification/qwen36-v1/submission-gate.json"),
            "sha256": SUBMISSION_GATE_SHA256,
        },
        "suite_reference": {
            "path": str(ROOT / "qualification/qwen36-v1/suite-reference.json"),
            "sha256": SUITE_REFERENCE_SHA256,
        },
        "synthetic_memory_smoke": {
            "authorized_by_qualification_pass": decision == "PASS",
            "gpu_run_submitted": False,
            "status_at_qualification_record": "AUTHORIZED_FOR_CPU_PREPARATION",
        },
        "technical_invalid_history": technical_history,
        "technical_invalid_run_count": len(technical_history),
        "technical_rerun_lineage": {
            "qualification": ["25953", "25963", "26036", "26053"],
            "smoke": ["25933", "25938", "25940"],
        },
        "termination_reason_distribution": dict(sorted(terminations.items())),
        "totals": {
            "agent_requests": sum(task["model_request_count"] for task in tasks),
            "agent_wall_time_seconds": sum(task["wall_time_seconds"] for task in tasks),
            "completion_tokens": sum(task["completion_tokens"] for task in tasks),
            "model_tokens": sum(
                task["prompt_tokens"] + task["completion_tokens"] for task in tasks
            ),
            "prompt_tokens": sum(task["prompt_tokens"] for task in tasks),
            "slurm_elapsed_seconds": sum(
                task["slurm"]["elapsed_seconds"] for task in tasks
            ),
        },
        "treatment": "no_memory",
    }
    write_canonical_json(RESULT_PATH, result)
    if RESULT_PATH.read_bytes() != canonical_json_bytes(result):
        raise RuntimeError("qualification result serialization is not canonical")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render_report(result), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "competence_passes": competence_passes,
                "decision": decision,
                "report": str(REPORT_PATH),
                "report_sha256": sha256_file(REPORT_PATH),
                "result": str(RESULT_PATH),
                "result_sha256": sha256_file(RESULT_PATH),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

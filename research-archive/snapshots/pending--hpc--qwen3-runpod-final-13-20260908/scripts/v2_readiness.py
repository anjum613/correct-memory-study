#!/usr/bin/env python3
"""Build the machine-readable V2 audit and conservative readiness decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any
import xml.etree.ElementTree as ET

from cmpilot.repository_manager import repository_content_digest


ROOT = Path(__file__).parents[1]
ARTIFACT = ROOT / "artifacts/v2-preflight"
HISTORICAL_FAMILY_ROOTS = {
    "axios-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-mcp-pinot-v01/families/axios-v1"
    ),
    "aim-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-aim-v01/families/aim-v1"
    ),
    "httpx-v1": Path(
        "/home/s224049759/projects/correct-memory-study-worktrees/"
        "track-b-httpx-v01/families/httpx-v1"
    ),
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _write(path: Path, value: Any) -> str:
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _issue(
    number: int,
    name: str,
    classification: str,
    current: str,
    evidence: list[str],
    v1: str,
    v2: str,
    correction: str,
    implemented: bool,
    tests: list[str],
) -> dict[str, Any]:
    return {
        "number": number,
        "issue": name,
        "classification": classification,
        "current_implementation": current,
        "evidence": evidence,
        "v1_affected": v1,
        "v2_affected": v2,
        "exact_correction": correction,
        "correction_implemented": implemented,
        "tests": tests,
    }


def issue_audit() -> list[dict[str, Any]]:
    exact = "tests/test_v2_preflight.py"
    census = "artifacts/v2-preflight/token-census-qwen.json; token-census-devstral.json"
    controls = "artifacts/v2-preflight/control-matrix.json"
    return [
        _issue(1, "context-window imbalance", "ACTUAL_V1_DESIGN_DEFECT", "V1 gave every condition the same 4096-token physical window; memory reduced usable trajectory capacity.", ["configs/agent/mini_swe_agent_smoke.yaml", "post-primary-strengthening-v1/context/context-budget-summary.json"], "YES: eight treated initial prompts had negative completion capacity.", "V2 accounting support fixed; execution integration remains blocked.", "Use a common post-ingestion B with P+B+R<=C.", True, [exact, census]),
        _issue(2, "prompt-token accounting", "NOT_A_DEFECT", "V1 counts every complete request using the model-native serialized prompt before sending it.", ["src/cmpilot/integrations/miniswe/vllm_text_model.py:274", "src/cmpilot/devstral_serialization.py"], "No counting defect found; separate memory-only counts were absent from analysis artifacts.", "Exact P/T accounting passes offline.", "Retain exact per-model counters and log P explicitly.", True, [exact, census]),
        _issue(3, "whole-trajectory usable capacity", "ACTUAL_V1_DESIGN_DEFECT", "V1 enforces only remaining physical request capacity, not an equal post-ingestion trajectory allowance.", ["src/cmpilot/integrations/miniswe/context_budget.py:113", "configs/agent/mini_swe_agent_smoke.yaml"], "YES.", "V2 ledger implements B=16384.", "Compute D_t=T_t-P and A_t=B-D_t every turn.", True, [exact]),
        _issue(4, "tool-output contribution to context", "NOT_A_DEFECT", "Visible observations are appended to history and included in the next exact request count; full output is separately logged in V1.", ["src/cmpilot/integrations/miniswe/adapter_runtime.py:57", "src/cmpilot/integrations/miniswe/vllm_text_model.py:274"], "No exclusion from token accounting found.", "V2 adds byte-exact bounded visibility and raw hashes.", "Keep all visible bytes in history; preserve raw output externally.", True, [exact]),
        _issue(5, "model-specific tokenizers", "TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED", "The latest V1 path has exact Qwen HF and Devstral mistral-common counters.", ["src/cmpilot/integrations/miniswe/context_budget.py", "src/cmpilot/devstral_serialization.py"], "Early Devstral infrastructure was amended before final use.", "Both exact counters produced all 24 cells.", "Pin tokenizer files and hashes per revision.", True, [census]),
        _issue(6, "chat templates", "TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED", "Qwen uses apply_chat_template(add_generation_prompt=True); Devstral uses mistral-common/tekken.", ["src/cmpilot/integrations/miniswe/context_budget.py:221", "src/cmpilot/devstral_serialization.py:130"], "The model-native divergence is intentional after the Devstral amendment.", "PASS offline.", "Retain native serialization and compare server/local counts on GPU.", True, [census, "GPU equality NOT_TESTED_NO_GPU"]),
        _issue(7, "generation ceiling", "INTERPRETATION_LIMITATION", "V1 max_tokens=512 per decision.", ["configs/agent/mini_swe_agent_smoke.yaml"], "Potentially constrained behavior, but not proven to create a treatment contrast.", "V2 G=4096 with dynamic A_t cap.", "Use max_new_tokens=min(G,A_t).", True, [exact]),
        _issue(8, "step limit", "INTERPRETATION_LIMITATION", "V1 maximum is 15 decisions.", ["configs/agent/mini_swe_agent_smoke.yaml"], "A fixed ceiling limits interpretation; most primary endings were context exhaustion.", "V2 S=32; GPU behavior untested.", "Treat step exhaustion as scientific.", True, [exact]),
        _issue(9, "agent wall limit", "NOT_A_DEFECT", "V1 has 450s agent and 600s outer bounds with preserved timeout evidence.", ["configs/agent/mini_swe_agent_smoke.yaml", "src/cmpilot/final_model_runtime.py:76"], "No silent unbounded execution found.", "V2 profile uses 1800s; qualification pending.", "Keep explicit layered timeouts and log them.", True, ["configs/v2/runtime.json"]),
        _issue(10, "command timeout", "INTERPRETATION_LIMITATION", "V1 command timeout is 60s.", ["configs/agent/mini_swe_agent_smoke.yaml"], "May constrain long model-chosen commands; timeout classification was the actual policy defect.", "V2 keeps 60s and makes model-chosen timeout scientific.", "Log command duration and timeout outcome.", True, [exact, "tests/test_v2_qualification.py"]),
        _issue(11, "model-server timeouts", "TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED", "Latest V1 has bounded connect/read, startup, allocation and attestation timeouts.", ["src/cmpilot/mini_swe_config.py:302", "src/cmpilot/final_model_runtime.py:76"], "Earlier Devstral startup failures received technical amendments and preserved replacements.", "V2 values explicit; real server test pending.", "Retain bounded phase-specific timeouts.", True, ["GPU NOT_TESTED_NO_GPU"]),
        _issue(12, "deterministic decoding", "NOT_A_DEFECT", "V1 requests temperature=0 and vLLM server seed=0.", ["src/cmpilot/experiment_models.py:586", "src/cmpilot/experiment_models.py:583"], "Greedy decoding was configured.", "V2 makes temperature=0, do_sample=false, top_p=1 explicit.", "Run three excluded-task repetitions on target server.", True, ["configs/v2/runtime.json", "GPU NOT_TESTED_NO_GPU"]),
        _issue(13, "seed effectiveness", "INTERPRETATION_LIMITATION", "V1 run seeds were identity/randomization fields; request seed was null under greedy decoding.", ["src/cmpilot/experiment_models.py:213", "post-primary-strengthening-v1/seed-diversity/seed-diversity-summary.md"], "Seeds did not create independent stochastic draws.", "No repeated study seeds invented.", "Treat runs as deterministic replicates and qualify repeatability.", True, ["GPU NOT_TESTED_NO_GPU"]),
        _issue(14, "task-completion semantics", "ACTUAL_V1_DESIGN_DEFECT", "Every invalidated target already satisfies the requested behavior and faithful reuse is NO_CHANGE_BASELINE.", ["families/*-v1/tasks/target-task.md", "families/*-v1/references/faithful-reuse/reference.json"], "YES: no action can count as functional success.", "BLOCKED: final-state identifiability is impossible under the required matrix.", "Prospectively redesign tasks or revise the required control semantics; neither is authorized here.", False, [controls, "src/cmpilot/v2_task_completion.py"]),
        _issue(15, "functionality-oracle semantics", "ACTUAL_V1_DESIGN_DEFECT", "V1 oracles test continued target behavior, not whether the requested engineering task was completed.", ["families/*-v1/oracles/functional/evaluate.py", controls], "YES.", "V1 oracle preserved; TASK_COMPLETION cannot be identified for these frozen tasks.", "Keep V1_FUNCTIONALITY and TASK_COMPLETION separate.", False, [controls]),
        _issue(16, "empty-patch/no-op semantics", "ACTUAL_V1_DESIGN_DEFECT", "Untouched, empty, irrelevant and faithful states all pass V1 functionality in all six families.", [controls, "post-primary-strengthening-v1/analysis-summary.md:19"], "YES: 46/48 final patches were empty.", "BLOCKED by state identity.", "Require prospective task fixtures where untouched fails and both implementation controls pass.", False, [controls]),
        _issue(17, "security witness integrity", "NOT_A_DEFECT", "Witnesses were externally held, hash-bound and unchanged; safe and unsafe controls show the frozen contrast.", ["families/*-v1/oracles/manifest.json", "artifacts/v2-preflight/v1-immutability.json"], "No outcome-conditioned witness change found.", "Security controls PASS.", "Continue hash binding and external evaluation.", True, [controls]),
        _issue(18, "treatment construction", "ACTUAL_V1_DESIGN_DEFECT", "NO_MEMORY injects nothing; memory injects exact frozen bytes, but usable context differed and the wrapper was non-neutral.", ["src/cmpilot/mcp_pinot_backend.py:450", "src/cmpilot/mcp_pinot_backend.py:501"], "YES.", "V2 neutral wrapper and common B implemented.", "Differ only in exact memory availability; do not pad.", True, ["tests/test_v2_prompting.py", census]),
        _issue(19, "memory rendering", "ACTUAL_V1_DESIGN_DEFECT", "V1 labels content SOURCE_CORRECT_PROCEDURAL_MEMORY, cueing source/correctness.", ["src/cmpilot/mcp_pinot_backend.py:70"], "YES as a cueing limitation.", "V2 uses ADDITIONAL_TASK_CONTEXT without changing memory bytes.", "Use the prospectively fixed neutral wrapper.", True, ["tests/test_v2_prompting.py"]),
        _issue(20, "model adapter parity", "NOT_A_DEFECT", "Both models share the same text-action loop, policies, repository and evaluator path; only native serialization/server loader differ.", ["src/cmpilot/final_model_runtime.py", "src/cmpilot/devstral_mini_swe_adapter.py"], "No accidental scientific-path asymmetry found in latest V1.", "Static V2 profiles are aligned; GPU parity untested.", "Qualify both exact servers with the same synthetic checklist.", True, ["tests/test_v2_qualification.py", "GPU NOT_TESTED_NO_GPU"]),
        _issue(21, "technical-invalid policy", "ACTUAL_V1_DESIGN_DEFECT", "V1 often derives technical validity from process exit/adapter metrics, so model-produced malformed/limit outcomes can be invalid.", ["src/cmpilot/final_model_runtime.py:337"], "YES: scientific and infrastructure causes are not cleanly separated.", "V2 exhaustive policy added.", "Classify listed model outcomes scientific and infrastructure failures technical invalid.", True, [exact]),
        _issue(22, "replacement policy", "NOT_A_DEFECT", "Attempts are atomically reserved in new slurm-<job> directories and old attempts are never reused.", ["src/cmpilot/final_experiment.py:1363"], "No overwrite defect found.", "V2 log writer also refuses overwrite.", "Preserve every attempt and allocate a new path.", True, ["tests/test_v2_logging.py"]),
        _issue(23, "trajectory logging", "INTERPRETATION_LIMITATION", "V1 preserves trajectories, transports, patches and full command output, but omits several requested reconstruction fields and per-command raw hashes.", ["src/cmpilot/integrations/miniswe/adapter_runtime.py:57", "post-primary-strengthening-v1/output-manifest.json"], "Analysis is possible but not fully self-describing.", "V2 schema enforces requested metadata; live integration untested.", "Populate V2RunLog from the eventual runner.", True, ["tests/test_v2_logging.py"]),
        _issue(24, "leakage/blinding", "UNRESOLVED", "Agent repositories omit oracles/references and command authorization blocks declared paths, but same-user filesystem access is not an OS security boundary.", ["src/cmpilot/integrations/miniswe/command_authorization.py:436", "families/*-v1/task-policy.json"], "No observed leakage, but containment is policy-level.", "UNRESOLVED until a mount/container test proves hidden paths inaccessible.", "Run agents in a sandbox exposing only the working copy and required runtime.", False, ["tests/test_command_authorization.py", "OS isolation NOT_TESTED"]),
    ]


def architecture_map() -> list[dict[str, str]]:
    paths = {
        "experiment entrypoints": "scripts/run_final_experiment.py -> cmpilot.final_runner",
        "model server startup": "src/cmpilot/final_model_runtime.py service classes",
        "Qwen adapter/profile": "src/cmpilot/experiment_models.py; integrations/miniswe/context_budget.py",
        "Devstral adapter/profile": "src/cmpilot/devstral_profile.py; devstral_serialization.py",
        "task/family loader": "src/cmpilot/final_runtime_backends.py and six family backends",
        "memory rendering": "each family backend _memory_treatment/apply_treatment",
        "prompt construction": "integrations/miniswe/action_protocol.py and backend rendered_task",
        "tokenizer usage": "ExactQwenChatTokenCounter / ExactMistralChatTokenCounter",
        "chat templates": "HF apply_chat_template / mistral-common encode_chat_completion",
        "generation parameters": "experiment_models.GenerationSettings -> VllmTextModel",
        "context and max_new_tokens": "integrations/miniswe/context_budget.py",
        "step/wall/command limits": "mini_swe_agent_smoke.yaml plus final_model_runtime.py",
        "HTTP timeouts": "mini_swe_config.py -> openai_transport.py",
        "tool output/transcript": "adapter_runtime.AuditedLocalEnvironment and mini-SWE history",
        "technical invalid classification": "final_model_runtime.classify_mini_swe_execution",
        "replacement/run IDs": "final_experiment.reserve_run_attempt and generated matrices",
        "trajectory/patch logging": "adapter_runtime.py; repository_manager.py; family backends",
        "functionality/security": "family external oracles invoked by family backends",
        "controls": "families/*/references and validation records",
        "leakage protections": "task-policy.json; command_authorization.py; protected-path checks",
        "aggregation": "scripts/aggregate_final_experiment.py and final_reporting.py",
        "seed handling": "experiment matrices; server seed=0; request seed null",
    }
    return [{"component": key, "implementation": value} for key, value in paths.items()]


def historical_snapshot_audit() -> dict[str, Any]:
    rows = []
    for family, historical_root in HISTORICAL_FAMILY_ROOTS.items():
        clean_root = ROOT / "families" / family
        inputs = _load(clean_root / "family-package.json")["inputs"]
        for state, key in (
            ("source", "source_repository"),
            ("compatible", "compatible_repository"),
            ("invalidated", "target_repository"),
        ):
            expected = inputs[key]["sha256"]
            clean = repository_content_digest(
                clean_root / "repositories" / state
            ).sha256
            historical = repository_content_digest(
                historical_root / "repositories" / state
            ).sha256
            rows.append(
                {
                    "family": family,
                    "state": state,
                    "manifest_sha256": expected,
                    "clean_checkout_sha256": clean,
                    "historical_worktree_sha256": historical,
                    "clean_checkout_matches": clean == expected,
                    "historical_worktree_matches": historical == expected,
                }
            )
    return {
        "status": "FAIL",
        "defect": "ignored family files were used in V1 but were not committed",
        "rows": rows,
        "frozen_families_modified": False,
    }


def _pytest_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "BLOCKED", "reason": "full-suite JUnit artifact absent"}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    totals["status"] = (
        "PASS" if totals["failures"] == 0 and totals["errors"] == 0 else "FAIL"
    )
    return totals


def test_execution_summary(output_root: Path) -> dict[str, Any]:
    disjoint = (
        "pytest-nonmount.xml",
        "pytest-remainder.xml",
        "pytest-final-third.xml",
        "pytest-tail.xml",
        "pytest-tail2.xml",
    )
    totals = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
    failures: list[str] = []
    v2_tests = 0
    v2_failures = 0
    for name in disjoint:
        path = output_root / name
        if not path.is_file():
            return {"status": "BLOCKED", "reason": f"missing disjoint JUnit: {name}"}
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        for key in totals:
            totals[key] += sum(int(suite.attrib.get(key, 0)) for suite in suites)
        for case in root.iter("testcase"):
            classname = str(case.attrib.get("classname", ""))
            failed = case.find("failure") is not None or case.find("error") is not None
            if failed:
                failures.append(f"{classname}.{case.attrib.get('name', '')}")
            if classname.startswith("tests.test_v2_"):
                v2_tests += 1
                v2_failures += int(failed)
    focused_name = "pytest-v2-focused.xml"
    focused = _pytest_summary(output_root / focused_name)
    return {
        **totals,
        "status": "FAIL" if totals["failures"] or totals["errors"] else "PASS",
        "collected_full_suite": 947,
        "executed_disjoint": totals["tests"],
        "not_executed_due_uninterruptible_environment_mount": 947 - totals["tests"],
        "full_suite_attempted": True,
        "interrupt_reason": (
            "frozen environment interpreters entered uninterruptible D state on network storage"
        ),
        "failure_tests": failures,
        "failure_groups": {
            "incomplete_committed_family_snapshots": 13,
            "historical_job_25692_python_environment": 2,
            "frozen_environment_mount_timeouts": 4,
        },
        "v2_tests": v2_tests,
        "v2_failures": v2_failures,
        "latest_focused_v2": focused,
        "junit_files": list(disjoint),
        "focused_junit_file": focused_name,
    }


def build(output_root: Path) -> dict[str, Any]:
    v1 = _load(output_root / "v1-immutability.json")
    qwen = _load(output_root / "token-census-qwen.json")
    devstral = _load(output_root / "token-census-devstral.json")
    controls = _load(output_root / "control-matrix.json")
    hardware = _load(output_root / "hardware-estimates.json")
    q_qualification = _load(output_root / "qualification-qwen.json")
    d_qualification = _load(output_root / "qualification-devstral.json")
    tests = test_execution_summary(output_root)
    _write(output_root / "test-results.json", tests)
    issues = issue_audit()
    issue_hash = _write(output_root / "v1-24-issue-audit.json", {"issues": issues})
    _write(output_root / "architecture-map.json", {"components": architecture_map()})
    _write(output_root / "historical-snapshot-audit.json", historical_snapshot_audit())
    leakage = {
        "status": "UNRESOLVED",
        "agent_copy_excludes_oracles_and_references": True,
        "command_policy_blocks_declared_hidden_paths": True,
        "evaluator_is_final_state_external": True,
        "os_level_mount_or_container_isolation_proven": False,
        "remaining_action": "qualify a sandbox exposing only working copy and runtime",
    }
    _write(output_root / "leakage-audit.json", leakage)
    all_fit = all(row["fits_32768"] for data in (qwen, devstral) for row in data["cells"])
    task_ready = all(
        state["TASK_COMPLETION"].get("status") != "BLOCKED_NON_IDENTIFIABLE"
        for family in controls["families"]
        for state in family["states"].values()
        if "TASK_COMPLETION" in state
    )
    security_ready = all(
        family["states"]["SAFE_CONTROL"]["SECURITY"].get("passed") is True
        and family["states"]["UNTOUCHED_I"]["SECURITY"].get("passed") is False
        for family in controls["families"]
    )
    q_hw, d_hw = hardware["models"]
    blockers = [
        "TASK_COMPLETION is non-identifiable: faithful reuse equals untouched I in all six families",
        "Axios, Aim and HTTPX committed family snapshots omit ignored files used by V1",
        "OS-level leakage isolation is not proven",
        "Qwen 32K model-server qualification is NOT_TESTED_NO_GPU",
        "Devstral 32K model-server qualification is NOT_TESTED_NO_GPU",
        "three-repeat deterministic server qualification is NOT_TESTED_NO_GPU",
    ]
    if tests.get("status") != "PASS":
        blockers.append("the complete non-study pytest suite is not PASS")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    readiness = {
        "protocol_version": "correct-memory-v2-preflight-1",
        "git_commit": commit,
        "v1_manifest_hash": hashlib.sha256(
            (output_root / "v1-immutability.json").read_bytes()
        ).hexdigest(),
        "issue_audit_hash": issue_hash,
        "all_tests_pass": tests.get("status") == "PASS",
        "test_summary": tests,
        "task_completion_ready": task_ready,
        "security_controls_ready": security_ready,
        "token_census_ready": len(qwen["cells"]) + len(devstral["cells"]) == 24,
        "all_prompts_fit_32768": all_fit,
        "qwen_qualification_status": q_qualification["overall_status"],
        "devstral_qualification_status": d_qualification["overall_status"],
        "leakage_audit_status": leakage["status"],
        "determinism_status": "NOT_TESTED_NO_GPU",
        "recommended_physical_context": 32768 if all_fit else None,
        "estimated_qwen_min_vram_gb": round(q_hw["estimated_total_vram_gib"], 2),
        "estimated_devstral_min_vram_gb": round(d_hw["estimated_total_vram_gib"], 2),
        "recommended_qwen_physical_vram_gb": 94,
        "recommended_devstral_physical_vram_gb": 80,
        "remaining_blockers": blockers,
        "study_run_authorized": False,
    }
    _write(output_root / "readiness.json", readiness)
    return readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ARTIFACT)
    args = parser.parse_args()
    value = build(args.output_root)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

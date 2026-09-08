#!/usr/bin/env python3
"""Build model-free development evidence for source pairing.

The pairing phase reads only the five audited public B roots and the frozen
source corpus.  This script never calls a model and never enumerates an unseen
target.  Source validation uses clean Git archives at the strict parent of the
five development anchors.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

from cmpilot.source_pairing import (
    _CONTINUOUS_FEATURES,
    AuditedWorkspaceReader,
    SourcePairingError,
    build_b_only_representation,
    calibrate_threshold,
    canonical_json,
    classify_task_statement,
    extract_python_symbol,
    rank_sources,
    select_top_source,
    source_feature_record,
    stable_record_hash,
)
from cmpilot.source_validation import (
    SOURCE_ENTRY_REQUIRED_FIELDS,
    corpus_manifest_hash,
    file_hash,
    git_output,
    git_repository_evidence,
    run_evidence_command,
    source_tree_evidence,
    validate_source_entry,
    validate_timestamp,
)
from cmpilot.susvibes_feasibility import (
    DEVELOPMENT_IDS,
    SUSVIBES_REVISION,
    SUSVIBES_TAG,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs/v2/context-dependent-memory-source-corpus-development-v1.json"
DEFAULT_REPOSITORIES = ROOT / "tmp/context-dependent-memory-source-pairing/source-repositories"
DEFAULT_MATERIALIZATIONS = ROOT / "tmp/context-dependent-memory-source-pairing/evidence-source-trees-v1"
DEFAULT_PUBLIC = ROOT / "tmp/context-dependent-memory-source-pairing/b-public"
DEFAULT_OUTPUT = ROOT / "artifacts/context-dependent-memory-source-pairing"
DEFAULT_FEASIBILITY_WORKTREE = Path(
    "/home/s224049759/projects/correct-memory-study-worktrees/"
    "v2-context-dependent-memory-susvibes-feasibility"
)
PAIRING_PROTOCOL_COMMIT = "52a76c63dcaa653625cda5d1ce03c221938ed53b"

RUNTIME_ROOTS = {
    DEVELOPMENT_IDS[0]: "tmp/susvibes-development-runtime-v2",
    DEVELOPMENT_IDS[1]: "tmp/susvibes-development-runtime-v2",
    DEVELOPMENT_IDS[2]: "tmp/susvibes-development-runtime-v2",
    DEVELOPMENT_IDS[3]: "tmp/susvibes-development-runtime-django-infra-retry-1",
    DEVELOPMENT_IDS[4]: "tmp/susvibes-development-runtime-requests-infra-retry-3",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def run_checked(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command!r}\n{result.stdout}{result.stderr}"
        )


def clean_archive(repository: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite evidence tree; choose a new root: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    archive = destination.parent / f".{destination.name}.tar"
    if archive.exists():
        raise FileExistsError(archive)
    run_checked(
        ["git", "-C", str(repository), "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
    )
    run_checked(["tar", "-xf", str(archive), "-C", str(destination)], cwd=ROOT)
    archive.unlink()
    return source_tree_evidence(destination)


def target_timestamps(
    config: Mapping[str, Any], repositories_root: Path
) -> tuple[dict[str, int], dict[str, str]]:
    epochs: dict[str, int] = {}
    renderings: dict[str, str] = {}
    for repository_name, repository_spec in config["repositories"].items():
        target_id = repository_spec["runtime_target"]
        repository = repositories_root / repository_name
        anchor = repository_spec["development_anchor"]
        epochs[target_id] = int(git_output(repository, "show", "-s", "--format=%ct", anchor))
        renderings[target_id] = git_output(
            repository, "show", "-s", "--format=%cI", anchor
        )
    if set(epochs) != set(DEVELOPMENT_IDS):
        raise RuntimeError("target timestamps do not cover exact development set")
    return epochs, renderings


def rootfs_for(feasibility_worktree: Path, target_id: str) -> Path:
    candidate = (
        feasibility_worktree
        / RUNTIME_ROOTS[target_id]
        / "cases"
        / target_id
        / "rootfs"
    )
    if not candidate.is_dir():
        raise FileNotFoundError(candidate)
    return candidate.resolve()


def runtime_command(
    *, launcher: Path, rootfs: Path, source_tree: Path, shell_command: str
) -> list[str]:
    return [
        str(launcher),
        str(rootfs),
        str(source_tree),
        "/bin/bash",
        "-lc",
        f"cd /project && {shell_command}",
    ]


def evidence_paths(candidate: Mapping[str, Any]) -> list[str]:
    return [candidate["test_path"], *candidate.get("additional_test_paths", [])]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "cmpilot-source-corpus-entry-v1",
        "title": "Executable focal-safe source corpus entry",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(SOURCE_ENTRY_REQUIRED_FIELDS),
        "properties": {
            name: {"description": "Required by frozen development protocol"}
            for name in sorted(SOURCE_ENTRY_REQUIRED_FIELDS)
        },
        "invariants": {
            "timestamp": "source commit epoch <= target B commit epoch",
            "correctness": "source_build and source_task_test are PASS",
            "focal_safety": "level A, B, or C; no global-security claim",
            "source_tier": "target-relative mapping over the exact five development IDs",
            "task_provenance": "copied exact upstream test node",
        },
    }


def build_environment(
    *,
    public_root: Path,
    target_id: str,
    rootfs: Path,
    launcher: Path,
    source_tree_hash: str,
) -> dict[str, Any]:
    public_metadata = load_json(public_root / target_id / "public-metadata.json")
    return {
        "adapter": "unprivileged namespace/chroot over pinned expanded rootfs",
        "container_manifest_digest": public_metadata["b_image_manifest_digest"],
        "container_image_name": public_metadata["image_name"],
        "rootfs_role": "PINNED_SUSVIBES_DEVELOPMENT_ENVIRONMENT",
        "rootfs_path": str(rootfs),
        "rootfs_launcher_sha256": sha256_file(launcher),
        "tested_source_tree_sha256": source_tree_hash,
        "network_during_test": "ISOLATED_BY_ROOTFS_ADAPTER_DEFAULTS",
        "evaluated_model_inference": False,
    }


def artifact_hashes(source_tree: Path, paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in paths:
        path = source_tree / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        hashes[relative] = file_hash(path)
    return hashes


def build_entry(
    *,
    candidate: Mapping[str, Any],
    repository_name: str,
    repository_spec: Mapping[str, Any],
    repository: Path,
    source_tree: Path,
    repository_evidence: Mapping[str, Any],
    source_tree_evidence_value: Mapping[str, Any],
    public_root: Path,
    target_epochs: Mapping[str, int],
    target_timestamp_renderings: Mapping[str, str],
    launcher: Path,
    feasibility_worktree: Path,
    build_cache: dict[tuple[str, str], dict[str, Any]],
    test_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    source_path = source_tree / candidate["source_file"]
    source_text = source_path.read_text(encoding="utf-8")
    implementation, implementation_start, implementation_end = extract_python_symbol(
        source_text, candidate["source_symbol"]
    )
    task_path = source_tree / candidate["test_path"]
    task_text = task_path.read_text(encoding="utf-8")
    source_task, task_start, task_end = extract_python_symbol(
        task_text, candidate["task_symbol"]
    )
    if candidate["source_file"] in {
        "aiohttp_session/__init__.py",
        "master/buildbot/www/resource.py",
        "wagtail/admin/rich_text/converters/contentstate.py",
        "django/contrib/auth/hashers.py",
        "requests/sessions.py",
    }:
        raise RuntimeError("candidate uses a frozen target-requested source file")

    runtime_target = repository_spec["runtime_target"]
    rootfs = rootfs_for(feasibility_worktree, runtime_target)
    environment = build_environment(
        public_root=public_root,
        target_id=runtime_target,
        rootfs=rootfs,
        launcher=launcher,
        source_tree_hash=source_tree_evidence_value["tree_sha256"],
    )

    build_shell = (
        "python -c \"from pathlib import Path; "
        f"compile(Path('{candidate['source_file']}').read_bytes(), "
        f"'{candidate['source_file']}', 'exec')\""
    )
    build_key = (repository_name, candidate["source_file"])
    if build_key not in build_cache:
        build_cache[build_key] = run_evidence_command(
            runtime_command(
                launcher=launcher,
                rootfs=rootfs,
                source_tree=source_tree,
                shell_command=build_shell,
            ),
            cwd=ROOT,
            environment_descriptor=environment,
            timeout_seconds=120,
        )
    test_shell = candidate["test_shell_command"]
    test_key = (repository_name, test_shell)
    if test_key not in test_cache:
        test_cache[test_key] = run_evidence_command(
            runtime_command(
                launcher=launcher,
                rootfs=rootfs,
                source_tree=source_tree,
                shell_command=test_shell,
            ),
            cwd=ROOT,
            environment_descriptor=environment,
            timeout_seconds=300,
        )
    build = build_cache[build_key]
    task_test = test_cache[test_key]

    all_test_paths = evidence_paths(candidate)
    evidence_hashes = artifact_hashes(
        source_tree, [candidate["source_file"], *all_test_paths]
    )
    license_path = source_tree / repository_spec["license_path"]
    source_artifact_hashes = {
        "license": file_hash(license_path),
        "source_file": evidence_hashes[candidate["source_file"]],
        "source_implementation": sha256_text(implementation),
        "source_task": sha256_text(source_task),
        **{f"source_test:{path}": evidence_hashes[path] for path in all_test_paths},
    }
    target_tiers = {
        target_id: ("S1" if target_id == runtime_target else "S3")
        for target_id in DEVELOPMENT_IDS
    }
    availability = {
        target_id: repository_evidence["commit_timestamp_epoch"] <= target_epochs[target_id]
        for target_id in DEVELOPMENT_IDS
    }
    for target_id, flag in availability.items():
        if flag:
            validate_timestamp(repository_evidence["commit_timestamp_epoch"], target_epochs[target_id])

    features = source_feature_record(implementation, source_task)
    entry = {
        "source_id": candidate["source_id"],
        "source_tier_by_target": target_tiers,
        "repository_url": repository_spec["url"],
        "repository_commit": repository_evidence["repository_commit"],
        "commit_timestamp": repository_evidence["commit_timestamp"],
        "commit_timestamp_epoch": repository_evidence["commit_timestamp_epoch"],
        "license": {
            "spdx": repository_spec["license_spdx"],
            "path": repository_spec["license_path"],
            "sha256": file_hash(license_path),
        },
        "language": "python",
        "build_system": repository_spec["build_system"],
        "environment": environment,
        "source_task_description": source_task,
        "source_task_provenance": {
            "kind": "UPSTREAM_TEST",
            "path": candidate["test_path"],
            "symbol": candidate["task_symbol"],
            "line_start": task_start,
            "line_end": task_end,
            "sha256": sha256_text(source_task),
        },
        "source_file": candidate["source_file"],
        "source_symbol": candidate["source_symbol"],
        "source_implementation_or_patch": implementation,
        **features,
        "source_test_paths": all_test_paths,
        "source_test_command": ["/bin/bash", "-lc", f"cd /project && {test_shell}"],
        "source_test_result": task_test["classification"],
        "source_build": build,
        "source_task_test": task_test,
        "focal_source_safety": {
            "classification": (
                "PASS" if task_test["classification"] == "PASS" else task_test["classification"]
            ),
            "level": candidate["safety_level"],
            "pstar": candidate["pstar"],
            "evidence_command": [
                "/bin/bash",
                "-lc",
                f"cd /project && {test_shell}",
            ],
            "evidence_paths": [candidate["source_file"], *all_test_paths],
            "evidence_hashes": evidence_hashes,
            "derived_without_target_oracle": True,
            "scope": "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY",
        },
        "source_environment_hash": stable_record_hash(environment),
        "source_artifact_hashes": source_artifact_hashes,
        "available_before_target_B": availability,
        "reconstruction": {
            "clone_command": [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                repository_spec["url"],
                repository_name,
            ],
            "fetch_command": [
                "git",
                "-C",
                repository_name,
                "fetch",
                "--depth=2",
                "origin",
                repository_spec["development_anchor"],
            ],
            "checkout_command": [
                "git",
                "-C",
                repository_name,
                "checkout",
                "--detach",
                repository_spec["source_commit"],
            ],
            "tree_sha256": source_tree_evidence_value["tree_sha256"],
            "file_count": source_tree_evidence_value["file_count"],
            "git_tree_object_sha1": repository_evidence["git_tree_object_sha1"],
            "source_line_start": implementation_start,
            "source_line_end": implementation_end,
            "target_B_timestamps": {
                target_id: {
                    "epoch": target_epochs[target_id],
                    "rfc3339": target_timestamp_renderings[target_id],
                }
                for target_id in DEVELOPMENT_IDS
            },
        },
    }
    validate_source_entry(entry, confirmatory=True)
    return entry


def build_attrition(
    *,
    candidate: Mapping[str, Any],
    repository_spec: Mapping[str, Any],
    source_tree: Path,
    source_tree_hash: str,
    public_root: Path,
    launcher: Path,
    feasibility_worktree: Path,
) -> dict[str, Any]:
    runtime_target = repository_spec["runtime_target"]
    rootfs = rootfs_for(feasibility_worktree, runtime_target)
    environment = build_environment(
        public_root=public_root,
        target_id=runtime_target,
        rootfs=rootfs,
        launcher=launcher,
        source_tree_hash=source_tree_hash,
    )
    build_shell = (
        "python -c \"from pathlib import Path; "
        f"compile(Path('{candidate['source_file']}').read_bytes(), "
        f"'{candidate['source_file']}', 'exec')\""
    )
    build = run_evidence_command(
        runtime_command(
            launcher=launcher,
            rootfs=rootfs,
            source_tree=source_tree,
            shell_command=build_shell,
        ),
        cwd=ROOT,
        environment_descriptor=environment,
        timeout_seconds=120,
    )
    attempts = []
    for attempt_spec in candidate["test_attempts"]:
        test = run_evidence_command(
            runtime_command(
                launcher=launcher,
                rootfs=rootfs,
                source_tree=source_tree,
                shell_command=attempt_spec["test_shell_command"],
            ),
            cwd=ROOT,
            environment_descriptor=environment,
            timeout_seconds=300,
        )
        if test["classification"] != attempt_spec["expected_classification"]:
            raise RuntimeError(
                f"attrition classification changed: {candidate['source_id']}: "
                f"{attempt_spec['label']}: {test['classification']}"
            )
        attempts.append(
            {
                "label": attempt_spec["label"],
                "reason": attempt_spec["reason"],
                "source_task_test": test,
            }
        )
    return {
        "source_id": candidate["source_id"],
        "repository": candidate["repository"],
        "candidate_status": "REJECTED_BEFORE_CORPUS",
        "reason": candidate["reason"],
        "selection_independent_of_semantic_outcome": True,
        "source_build": build,
        "source_task_test_attempts": attempts,
    }


def build_public_representations(public_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    representations: list[dict[str, Any]] = []
    cue_rows: list[dict[str, Any]] = []
    for target_id in DEVELOPMENT_IDS:
        reader = AuditedWorkspaceReader(public_root / target_id)
        representation = build_b_only_representation(reader)
        if any(event["decision"] != "ALLOW" for event in reader.events):
            raise RuntimeError("B-only build unexpectedly attempted a denied read")
        representations.append(
            {
                "target_id": target_id,
                "representation": representation,
                "representation_sha256": stable_record_hash(representation),
                "filesystem_read_audit": reader.events,
                "denied_read_count": 0,
            }
        )
        cue = classify_task_statement(representation["task_statement"])
        cue_rows.append(
            {
                "target_id": target_id,
                "official_task_sha256": sha256_text(representation["task_statement"]),
                "official_task_statement": representation["task_statement"],
                **cue,
            }
        )
    return representations, cue_rows


def matcher_evidence(
    *,
    representations: list[dict[str, Any]],
    entries: list[dict[str, Any]],
    target_epochs: Mapping[str, int],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    repository_by_source = {
        entry["source_id"]: entry["repository_url"] for entry in entries
    }
    target_rankings: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    for target_row in representations:
        target = target_row["representation"]
        target_id = target["benchmark_instance_id"]
        rows = rank_sources(target, entries, target_timestamp=target_epochs[target_id])
        for row in rows:
            label = "POSITIVE" if row["scores"]["operation_class_exact"] else "NEGATIVE"
            calibration_rows.append(
                {
                    "target_id": target_id,
                    "source_id": row["source_id"],
                    "source_repository": repository_by_source[row["source_id"]],
                    "label": label,
                    **{
                        feature: row["scores"][feature]
                        for feature in _CONTINUOUS_FEATURES
                    },
                }
            )
        target_rankings.append(
            {
                "target_id": target_id,
                "target_representation_sha256": target_row["representation_sha256"],
                "target_timestamp_epoch": target_epochs[target_id],
                "full_rankings": rows,
            }
        )

    feature_results = {
        feature: calibrate_threshold(calibration_rows, feature)
        for feature in _CONTINUOUS_FEATURES
    }
    all_features_freezeable = all(
        result["freezeable"] for result in feature_results.values()
    )
    thresholds = (
        {
            feature: float(feature_results[feature]["threshold"])
            for feature in _CONTINUOUS_FEATURES
        }
        if all_features_freezeable
        else {}
    )
    combined_accepted = [
        row
        for row in calibration_rows
        if row["label"] == "POSITIVE"
        and all(float(row[feature]) >= threshold for feature, threshold in thresholds.items())
    ]
    combined_repositories = sorted(
        {row["source_repository"] for row in combined_accepted}
    )
    combined_freezeable = all_features_freezeable and len(combined_repositories) >= 2

    margins: dict[str, float | None] = {}
    for feature in _CONTINUOUS_FEATURES:
        differences: list[float] = []
        for target in target_rankings:
            eligible = [
                row
                for row in target["full_rankings"]
                if row["hard_gate_pass"] and row["scores"]["operation_class_exact"]
            ]
            for left, right in zip(eligible, eligible[1:]):
                difference = float(left["scores"][feature]) - float(right["scores"][feature])
                if difference > 0:
                    differences.append(difference)
        margins[feature] = round(min(differences), 12) if differences else None

    diagnostic_margins = {
        feature: (value if value is not None else float("inf"))
        for feature, value in margins.items()
    }
    for target_row, ranking_row in zip(representations, target_rankings):
        target = target_row["representation"]
        try:
            rankings, lock = select_top_source(
                target,
                entries,
                target_timestamp=target_epochs[target["benchmark_instance_id"]],
                thresholds=thresholds if combined_freezeable else {},
                ambiguity_margins=diagnostic_margins,
            )
            if rankings != ranking_row["full_rankings"]:
                raise RuntimeError("matcher ranking changed within one build")
            ranking_row["development_selection"] = {
                "status": "LOCKED",
                "mode": (
                    "FROZEN_THRESHOLD_CANDIDATE"
                    if combined_freezeable
                    else "DIAGNOSTIC_NO_NUMERIC_THRESHOLD_NOT_CONFIRMATORY"
                ),
                "lock": lock,
            }
        except SourcePairingError as error:
            ranking_row["development_selection"] = {
                "status": "REJECTED",
                "mode": (
                    "FROZEN_THRESHOLD_CANDIDATE"
                    if combined_freezeable
                    else "DIAGNOSTIC_NO_NUMERIC_THRESHOLD_NOT_CONFIRMATORY"
                ),
                "reason": str(error),
            }

    calibration = {
        "schema": "cmpilot-matcher-calibration-v1",
        "development_only": True,
        "label_rule": "POSITIVE iff deterministic controlled operation classes intersect; otherwise NEGATIVE",
        "label_rule_uses_target_oracle": False,
        "rows": calibration_rows,
        "feature_distributions": {
            feature: {
                label: sorted(
                    float(row[feature])
                    for row in calibration_rows
                    if row["label"] == label
                )
                for label in ("POSITIVE", "NEGATIVE")
            }
            for feature in _CONTINUOUS_FEATURES
        },
        "feature_calibrations": feature_results,
    }
    threshold_candidate = {
        "schema": "cmpilot-matcher-threshold-candidate-v1",
        "development_only": True,
        "prospective_rule_commit": PAIRING_PROTOCOL_COMMIT,
        "thresholds": thresholds if combined_freezeable else None,
        "ambiguity_margins": margins,
        "individual_features_freezeable": all_features_freezeable,
        "combined_accepted_positive_count": len(combined_accepted) if all_features_freezeable else 0,
        "combined_accepted_source_repositories": (
            combined_repositories if all_features_freezeable else []
        ),
        "matcher_thresholds_freezeable": combined_freezeable,
        "decision": (
            "FREEZE_CANDIDATE"
            if combined_freezeable
            else "DO_NOT_FREEZE_INADEQUATE_SEPARATION"
        ),
    }
    rankings_artifact = {
        "schema": "cmpilot-matcher-development-rankings-v1",
        "development_only": True,
        "ranking_uses_target_oracle": False,
        "top_one": True,
        "rank_2_fallback": False,
        "targets": target_rankings,
    }
    return calibration, threshold_candidate, rankings_artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repositories-root", type=Path, default=DEFAULT_REPOSITORIES)
    parser.add_argument("--materializations-root", type=Path, default=DEFAULT_MATERIALIZATIONS)
    parser.add_argument("--public-root", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--feasibility-worktree", type=Path, default=DEFAULT_FEASIBILITY_WORKTREE
    )
    parser.add_argument(
        "--matcher-only",
        action="store_true",
        help="reuse the validated corpus artifact and rebuild only B-only matcher evidence",
    )
    args = parser.parse_args()

    config = load_json(args.config.resolve(strict=True))
    if config.get("development_only") is not True:
        raise RuntimeError("source corpus spec is not development-only")
    repositories_root = args.repositories_root.resolve(strict=True)
    public_root = args.public_root.resolve(strict=True)
    feasibility_worktree = args.feasibility_worktree.resolve(strict=True)
    output_root = args.output_root.resolve() if args.output_root.exists() else args.output_root.absolute()
    materializations_root = args.materializations_root.absolute()
    materializations_root.mkdir(parents=True, exist_ok=True)
    launcher = (ROOT / "scripts/susvibes_rootfs_exec.sh").resolve(strict=True)

    target_epochs, target_renderings = target_timestamps(config, repositories_root)
    representations, cue_rows = build_public_representations(public_root)

    if args.matcher_only:
        manifest = load_json(output_root / "source-corpus-manifest.json")
        entries = manifest["entries"]
        if corpus_manifest_hash(entries) != manifest["source_corpus_sha256"]:
            raise RuntimeError("existing source corpus hash mismatch")
        calibration, thresholds, rankings = matcher_evidence(
            representations=representations,
            entries=entries,
            target_epochs=target_epochs,
        )
        cue_artifact = {
            "schema": "cmpilot-task-statement-cue-development-v1",
            "development_only": True,
            "policy": "VERBATIM_OFFICIAL_TEXT_PLUS_ELIGIBILITY_REJECTION",
            "sanitization_rule": "NONE",
            "candidate_specific_editing_allowed": False,
            "ineligible_classes": [
                "EXPLICIT_SECURITY_REQUIREMENT",
                "FOCAL_PRECONDITION_CUE",
                "SAFE_IMPLEMENTATION_LEAKAGE",
            ],
            "future_rule": "Apply the same deterministic classifier to verbatim official text; reject any ineligible class and never rewrite task text.",
            "results": cue_rows,
            "eligible_count": sum(row["public_text_eligible"] for row in cue_rows),
            "rejected_count": sum(not row["public_text_eligible"] for row in cue_rows),
            "task_statement_cue_rule_ready": True,
        }
        representation_artifact = {
            "schema": "cmpilot-b-only-representation-results-v1",
            "development_only": True,
            "susvibes_revision": SUSVIBES_REVISION,
            "target_count": len(representations),
            "all_reads_audited": True,
            "oracle_fields_observed": False,
            "results": representations,
        }
        write_json(output_root / "task-statement-cue-development.json", cue_artifact)
        write_json(output_root / "b-only-representation-results.json", representation_artifact)
        write_json(output_root / "matcher-calibration.json", calibration)
        write_json(output_root / "matcher-threshold-candidate.json", thresholds)
        write_json(output_root / "matcher-development-rankings.json", rankings)
        print(
            json.dumps(
                {
                    "entries": len(entries),
                    "matcher_only": True,
                    "matcher_thresholds_freezeable": thresholds[
                        "matcher_thresholds_freezeable"
                    ],
                },
                sort_keys=True,
            )
        )
        return 0

    repository_evidence: dict[str, dict[str, Any]] = {}
    tree_evidence: dict[str, dict[str, Any]] = {}
    source_trees: dict[str, Path] = {}
    for repository_name, repository_spec in config["repositories"].items():
        repository = repositories_root / repository_name
        repository_evidence[repository_name] = git_repository_evidence(
            repository,
            expected_url=repository_spec["url"],
            expected_commit=repository_spec["source_commit"],
        )
        source_tree = materializations_root / repository_name
        tree_evidence[repository_name] = clean_archive(repository, source_tree)
        source_trees[repository_name] = source_tree

    entries: list[dict[str, Any]] = []
    build_cache: dict[tuple[str, str], dict[str, Any]] = {}
    test_cache: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in config["candidates"]:
        repository_name = candidate["repository"]
        entry = build_entry(
            candidate=candidate,
            repository_name=repository_name,
            repository_spec=config["repositories"][repository_name],
            repository=repositories_root / repository_name,
            source_tree=source_trees[repository_name],
            repository_evidence=repository_evidence[repository_name],
            source_tree_evidence_value=tree_evidence[repository_name],
            public_root=public_root,
            target_epochs=target_epochs,
            target_timestamp_renderings=target_renderings,
            launcher=launcher,
            feasibility_worktree=feasibility_worktree,
            build_cache=build_cache,
            test_cache=test_cache,
        )
        entries.append(entry)

    attrition = [
        build_attrition(
            candidate=candidate,
            repository_spec=config["repositories"][candidate["repository"]],
            source_tree=source_trees[candidate["repository"]],
            source_tree_hash=tree_evidence[candidate["repository"]]["tree_sha256"],
            public_root=public_root,
            launcher=launcher,
            feasibility_worktree=feasibility_worktree,
        )
        for candidate in config["attrition_candidates"]
    ]
    if len(entries) != len({entry["source_id"] for entry in entries}):
        raise RuntimeError("duplicate corpus source IDs")
    manifest_digest = corpus_manifest_hash(entries)
    calibration, thresholds, rankings = matcher_evidence(
        representations=representations,
        entries=entries,
        target_epochs=target_epochs,
    )

    manifest = {
        "schema": "cmpilot-source-corpus-manifest-v1",
        "status": "DEVELOPMENT_VALIDATED_FROZEN_CANDIDATE",
        "development_only": True,
        "generated_at_utc": utc_now(),
        "susvibes_tag": SUSVIBES_TAG,
        "susvibes_revision": SUSVIBES_REVISION,
        "pairing_protocol_commit": PAIRING_PROTOCOL_COMMIT,
        "source_spec_path": args.config.resolve().relative_to(ROOT).as_posix(),
        "source_spec_sha256": sha256_file(args.config),
        "source_corpus_entries": len(entries),
        "source_corpus_sha256": manifest_digest,
        "arbitrary_live_search_used": False,
        "s4_enabled": False,
        "repositories": repository_evidence,
        "entries": entries,
    }
    validation_results = {
        "schema": "cmpilot-source-validation-results-v1",
        "development_only": True,
        "source_corpus_sha256": manifest_digest,
        "qualified_count": len(entries),
        "candidate_count": len(entries) + len(attrition),
        "source_build_pass_count": sum(
            entry["source_build"]["classification"] == "PASS" for entry in entries
        ),
        "source_task_test_pass_count": sum(
            entry["source_task_test"]["classification"] == "PASS" for entry in entries
        ),
        "qualified": [
            {
                "source_id": entry["source_id"],
                "source_build": entry["source_build"],
                "source_task_test": entry["source_task_test"],
                "reconstruction": entry["reconstruction"],
                "source_artifact_hashes": entry["source_artifact_hashes"],
            }
            for entry in entries
        ],
        "attrition": attrition,
    }
    focal_results = {
        "schema": "cmpilot-source-focal-safety-results-v1",
        "development_only": True,
        "scope": "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY",
        "pass_count": len(entries),
        "eligible_levels": ["A", "B", "C"],
        "results": [
            {
                "source_id": entry["source_id"],
                **entry["focal_source_safety"],
            }
            for entry in entries
        ],
    }
    cue_artifact = {
        "schema": "cmpilot-task-statement-cue-development-v1",
        "development_only": True,
        "policy": "VERBATIM_OFFICIAL_TEXT_PLUS_ELIGIBILITY_REJECTION",
        "sanitization_rule": "NONE",
        "candidate_specific_editing_allowed": False,
        "ineligible_classes": [
            "EXPLICIT_SECURITY_REQUIREMENT",
            "FOCAL_PRECONDITION_CUE",
            "SAFE_IMPLEMENTATION_LEAKAGE",
        ],
        "future_rule": "Apply the same deterministic classifier to verbatim official text; reject any ineligible class and never rewrite task text.",
        "results": cue_rows,
        "eligible_count": sum(row["public_text_eligible"] for row in cue_rows),
        "rejected_count": sum(not row["public_text_eligible"] for row in cue_rows),
        "task_statement_cue_rule_ready": True,
    }
    representation_artifact = {
        "schema": "cmpilot-b-only-representation-results-v1",
        "development_only": True,
        "susvibes_revision": SUSVIBES_REVISION,
        "target_count": len(representations),
        "all_reads_audited": True,
        "oracle_fields_observed": False,
        "results": representations,
    }

    write_json(output_root / "source-corpus-schema.json", source_schema())
    write_json(output_root / "source-corpus-manifest.json", manifest)
    write_json(output_root / "source-validation-results.json", validation_results)
    write_json(output_root / "source-focal-safety-results.json", focal_results)
    write_json(output_root / "task-statement-cue-development.json", cue_artifact)
    write_json(output_root / "b-only-representation-results.json", representation_artifact)
    write_json(output_root / "matcher-calibration.json", calibration)
    write_json(output_root / "matcher-threshold-candidate.json", thresholds)
    write_json(output_root / "matcher-development-rankings.json", rankings)
    print(
        json.dumps(
            {
                "entries": len(entries),
                "attrition": len(attrition),
                "source_corpus_sha256": manifest_digest,
                "matcher_thresholds_freezeable": thresholds[
                    "matcher_thresholds_freezeable"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

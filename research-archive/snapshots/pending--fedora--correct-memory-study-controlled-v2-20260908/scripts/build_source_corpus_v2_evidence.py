#!/usr/bin/env python3
"""Build reproducible, model-free V2 source-corpus development evidence.

The script consumes only frozen V1 source evidence, ordinary pinned upstream
snapshots, and SusVibes instance IDs.  It does not read an unseen task row,
target workspace, U/R patch, security test, or evaluated-model output.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
from typing import Any, Mapping, Sequence

from cmpilot.memory_lifecycle import audit_memory_packet, render_memory_packet
from cmpilot.source_corpus_v2 import (
    INHERITED_V1_ENTRIES,
    NEW_CANDIDATE_ATTEMPT_CAP,
    PILOT_NEW_ATTEMPTS,
    PROTOCOL_ID,
    SUCCESSOR_PROTOCOL_COMMIT,
    choose_corpus_target,
    corpus_breadth,
    discover_source_candidates,
    round_robin_candidates,
    source_only_partition_assessment,
    source_universe_design,
)
from cmpilot.source_pairing import extract_python_symbol, stable_record_hash
from cmpilot.source_validation import (
    corpus_manifest_hash,
    file_hash,
    git_repository_evidence,
    run_evidence_command,
    source_tree_evidence,
    validate_source_entry,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, sha256_file


ROOT = Path(__file__).resolve().parents[1]
V1_ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"
FEASIBILITY_ROOT = ROOT / "artifacts/context-dependent-memory-susvibes-feasibility"
DEFAULT_OUTPUT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"
DEFAULT_CACHE = ROOT / "tmp/context-dependent-memory-source-pairing-v2"
FEASIBILITY_WORKTREE = Path(
    "/home/s224049759/projects/correct-memory-study-worktrees/"
    "v2-context-dependent-memory-susvibes-feasibility"
)

S1_TARGETS = {
    "aiohttp-session": DEVELOPMENT_IDS[0],
    "buildbot": DEVELOPMENT_IDS[1],
    "wagtail": DEVELOPMENT_IDS[2],
    "django": DEVELOPMENT_IDS[3],
    "requests": DEVELOPMENT_IDS[4],
}

ROOTFS_RELATIVE = {
    "aiohttp-session": "tmp/susvibes-development-runtime-v2",
    "buildbot": "tmp/susvibes-development-runtime-v2",
    "wagtail": "tmp/susvibes-development-runtime-v2",
    "django": "tmp/susvibes-development-runtime-django-infra-retry-1",
    "requests": "tmp/susvibes-development-runtime-requests-infra-retry-3",
}

S2_SPECS = (
    {
        "name": "airflow",
        "repository_url": "https://github.com/apache/airflow.git",
        "anchor": "ac65b82eeeeaa670e09a83c7da65cbac7e89f8db",
        "commit": "2a79fb74fd7203fe82b9384af42a59b3a41f84e9",
        "license_path": "LICENSE",
        "license_spdx": "Apache-2.0",
        "build_system": ["pyproject.toml", "setup.cfg"],
        "test_runner": "PYTEST_NODE",
        "venv": "airflow",
        "pythonpath": ".",
        "dependency_install": ["pytest==7.3.1"],
    },
    {
        "name": "starlette",
        "repository_url": "https://github.com/encode/starlette.git",
        "anchor": "1797de464124b090f10cf570441e8292936d63e3",
        "commit": "24c1fac62a80bb153c6548145334fc643991e35a",
        "license_path": "LICENSE.md",
        "license_spdx": "BSD-3-Clause",
        "build_system": ["pyproject.toml", "requirements.txt", "setup.cfg"],
        "test_runner": "PYTEST_NODE",
        "venv": "starlette",
        "pythonpath": ".",
        "dependency_install": [
            "pytest==7.3.1",
            "anyio==3.7.1",
            "httpx==0.24.1",
        ],
        "pytest_compatibility_args": ["-W", "ignore::DeprecationWarning"],
    },
    {
        "name": "ssh-audit",
        "repository_url": "https://github.com/jtesta/ssh-audit.git",
        "anchor": "8e972c5e94b460379fe0c7d20209c16df81538a5",
        "commit": "46eb970376393a9c8f2f3ffc728e90b948c83477",
        "license_path": "LICENSE",
        "license_spdx": "MIT",
        "build_system": ["pyproject.toml", "setup.cfg"],
        "test_runner": "PYTEST_NODE",
        "venv": "ssh-audit",
        "pythonpath": "src",
        "dependency_install": ["pytest==7.3.1"],
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite development evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def command_output(command: Sequence[str], *, cwd: Path) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {command!r}: {result.stderr}")
    return result.stdout.strip()


def dataset_instance_ids() -> tuple[str, ...]:
    universe = load_json(FEASIBILITY_ROOT / "unseen-target-universe.json")
    if universe["enumeration_fields_read"] != ["instance_id"]:
        raise RuntimeError("unseen enumeration exceeded instance_id")
    values = tuple([*universe["development_ids"], *universe["unseen_ids"]])
    if len(values) != 186 or len(set(values)) != 186:
        raise RuntimeError("SusVibes instance-ID universe changed")
    return values


def target_timestamps() -> dict[str, dict[str, Any]]:
    manifest = load_json(V1_ARTIFACT_ROOT / "source-corpus-manifest.json")
    values = manifest["entries"][0]["reconstruction"]["target_B_timestamps"]
    if set(values) != set(DEVELOPMENT_IDS):
        raise RuntimeError("development target timestamp set changed")
    return values


def source_specifications(config: Mapping[str, Any], cache: Path) -> list[dict[str, Any]]:
    values = []
    for spec in config["s1"]:
        name = spec["name"]
        values.append(
            {
                **spec,
                "tier": "S1",
                "repository": cache / "s1-repositories" / name,
                "source_tree": cache / "s1-trees" / name,
                "runtime_target": S1_TARGETS[name],
                "rootfs": (
                    FEASIBILITY_WORKTREE
                    / ROOTFS_RELATIVE[name]
                    / "cases"
                    / S1_TARGETS[name]
                    / "rootfs"
                ),
            }
        )
    for spec in S2_SPECS:
        values.append(
            {
                **spec,
                "tier": "S2",
                "repository": cache / "s2-repositories" / spec["name"],
                "source_tree": cache / "s2-trees" / spec["name"],
                "venv_path": cache / "venvs" / spec["venv"],
            }
        )
    return values


def validate_materializations(
    specs: Sequence[Mapping[str, Any]], universe: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    s2_order = {
        (row["repository_url"], row["anchor_commit"]): row["ordering_sha256"]
        for row in universe["s2_entries"]
    }
    expected_first = [
        (row["repository_url"], row["anchor_commit"])
        for row in universe["s2_entries"][: len(S2_SPECS)]
    ]
    observed_first = [(spec["repository_url"], spec["anchor"]) for spec in S2_SPECS]
    if observed_first != expected_first:
        raise RuntimeError("materialized S2 repositories are not the frozen queue prefix")
    for spec in specs:
        repository = Path(spec["repository"]).resolve(strict=True)
        source_tree = Path(spec["source_tree"]).resolve(strict=True)
        git_evidence = git_repository_evidence(
            repository,
            expected_url=spec["repository_url"],
            expected_commit=spec["commit"],
        )
        if spec["tier"] == "S2":
            observed_parent = command_output(
                ["git", "rev-parse", f"{spec['anchor']}^"], cwd=repository
            )
            if observed_parent != spec["commit"]:
                raise RuntimeError("S2 checkout is not strict first parent")
            git_evidence["anchor_commit"] = spec["anchor"]
            git_evidence["repository_order_sha256"] = s2_order[
                (spec["repository_url"], spec["anchor"])
            ]
        evidence[spec["name"]] = {
            "git": git_evidence,
            "tree": source_tree_evidence(source_tree),
        }
    return evidence


def environment_descriptor(
    spec: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    if spec["tier"] == "S1":
        public = load_json(
            ROOT
            / "targets/public/susvibes-development"
            / spec["runtime_target"]
            / "public-metadata.json"
        )
        launcher = ROOT / "scripts/susvibes_rootfs_exec.sh"
        return {
            "role": "PINNED_SUSVIBES_DEVELOPMENT_ROOTFS",
            "container_image_name": public["image_name"],
            "container_manifest_digest": public["b_image_manifest_digest"],
            "rootfs_path": str(Path(spec["rootfs"]).resolve(strict=True)),
            "launcher_sha256": sha256_file(launcher),
            "tested_source_tree_sha256": evidence["tree"]["tree_sha256"],
            "network_during_test": "ISOLATED_BY_ROOTFS_ADAPTER_DEFAULTS",
            "evaluated_model_inference": False,
        }
    venv = Path(spec["venv_path"]).resolve(strict=True)
    python = venv / "bin/python"
    freeze = command_output([str(python), "-m", "pip", "freeze", "--all"], cwd=ROOT)
    return {
        "role": "SOURCE_ONLY_LOCAL_VENV",
        "python": command_output([str(python), "--version"], cwd=ROOT),
        "python_path": str(python),
        "pip_freeze": freeze.splitlines(),
        "pip_freeze_sha256": hashlib.sha256((freeze + "\n").encode()).hexdigest(),
        "dependency_install": list(spec["dependency_install"]),
        "pytest_compatibility_args": list(
            spec.get("pytest_compatibility_args", ())
        ),
        "tested_source_tree_sha256": evidence["tree"]["tree_sha256"],
        "network_during_test": "NO_NETWORK_REQUIRED_BY_SELECTED_UPSTREAM_NODE",
        "evaluated_model_inference": False,
    }


def logical_test_command(spec: Mapping[str, Any], candidate: Mapping[str, Any]) -> str:
    path = candidate["source_task_provenance"]["path"]
    qualified = candidate["source_task_provenance"]["symbol"]
    runner = spec["test_runner"]
    if runner == "PYTEST_NODE":
        compatibility = " ".join(spec.get("pytest_compatibility_args", ()))
        compatibility = f" {compatibility}" if compatibility else ""
        return (
            f"python -m pytest -q -p no:cacheprovider{compatibility} "
            f"{path}::{qualified.replace('.', '::')}"
        )
    module = path.removesuffix(".py").replace("/", ".")
    if runner == "DJANGO_RUNTESTS_NODE":
        module = module.removeprefix("tests.")
        return f"python tests/runtests.py {module}.{qualified} -v 1"
    if runner == "WAGTAIL_RUNTESTS_NODE":
        return f"python runtests.py {module}.{qualified} -v 1"
    if runner == "TWISTED_TRIAL_NODE":
        module = module.removeprefix("master.")
        return f"cd master && python -m twisted.trial {module}.{qualified}"
    raise RuntimeError(f"unknown test runner: {runner}")


def execution_command(
    spec: Mapping[str, Any], source_tree: Path, shell_command: str
) -> tuple[list[str], Mapping[str, str] | None]:
    if spec["tier"] == "S1":
        return (
            [
                str((ROOT / "scripts/susvibes_rootfs_exec.sh").resolve(strict=True)),
                str(Path(spec["rootfs"]).resolve(strict=True)),
                str(source_tree),
                "/bin/bash",
                "-lc",
                f"cd /project && {shell_command}",
            ],
            None,
        )
    python = Path(spec["venv_path"]).resolve(strict=True) / "bin/python"
    command = shell_command.replace("python", str(python), 1)
    command = f"cd {shlex.quote(str(source_tree))} && {command}"
    environment = dict(os.environ)
    python_path = source_tree / spec["pythonpath"]
    environment.update(
        {
            "PYTHONPATH": str(python_path.resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
    )
    return (["/bin/bash", "-lc", command], environment)


def availability_and_tiers(
    spec: Mapping[str, Any], source_epoch: int, timestamps: Mapping[str, Any]
) -> tuple[dict[str, bool], dict[str, str]]:
    availability = {
        target_id: source_epoch <= int(record["epoch"])
        for target_id, record in timestamps.items()
    }
    if spec["tier"] == "S2":
        tiers = {target_id: "S2" for target_id in DEVELOPMENT_IDS}
    else:
        tiers = {
            target_id: ("S1" if target_id == spec["runtime_target"] else "S2")
            for target_id in DEVELOPMENT_IDS
        }
    return availability, tiers


def qualify_candidate(
    candidate: Mapping[str, Any],
    spec: Mapping[str, Any],
    evidence: Mapping[str, Any],
    timestamps: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    source_tree = Path(spec["source_tree"]).resolve(strict=True)
    environment = environment_descriptor(spec, evidence)
    source_file = candidate["source_file"]
    build_shell = (
        "python -c \"from pathlib import Path; "
        f"compile(Path('{source_file}').read_bytes(), '{source_file}', 'exec')\""
    )
    build_argv, build_env = execution_command(spec, source_tree, build_shell)
    build = run_evidence_command(
        build_argv,
        cwd=ROOT,
        environment_descriptor=environment,
        timeout_seconds=120,
        environment=build_env,
    )
    logical_test = logical_test_command(spec, candidate)
    test = None
    if build["classification"] == "PASS":
        test_argv, test_env = execution_command(spec, source_tree, logical_test)
        test = run_evidence_command(
            test_argv,
            cwd=ROOT,
            environment_descriptor=environment,
            timeout_seconds=300,
            environment=test_env,
        )
    qualified = bool(test and test["classification"] == "PASS")
    attempt = {
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "source_id": candidate["source_id"],
        "repository_url": spec["repository_url"],
        "repository_commit": spec["commit"],
        "tier": spec["tier"],
        "source_file": source_file,
        "source_symbol": candidate["source_symbol"],
        "source_task_path": candidate["source_task_provenance"]["path"],
        "source_task_symbol": candidate["source_task_provenance"]["symbol"],
        "source_build": build,
        "source_task_test": test,
        "classification": "QUALIFIED" if qualified else "ATTRITION",
        "attrition_reason": (
            None
            if qualified
            else (
                "SOURCE_BUILD_NOT_PASS"
                if build["classification"] != "PASS"
                else "SOURCE_TASK_TEST_NOT_PASS"
            )
        ),
        "candidate_generation_uses_target": False,
        "candidate_generation_uses_oracle": False,
        "candidate_generation_uses_model": False,
    }
    if not qualified:
        return None, attempt

    source_path = source_tree / source_file
    test_path = source_tree / candidate["source_task_provenance"]["path"]
    license_path = source_tree / spec["license_path"]
    implementation, implementation_start, implementation_end = extract_python_symbol(
        source_path.read_text(encoding="utf-8"), candidate["source_symbol"]
    )
    if implementation != candidate["source_implementation_or_patch"]:
        raise RuntimeError("candidate implementation bytes changed during qualification")
    source_epoch = int(evidence["git"]["commit_timestamp_epoch"])
    availability, tiers = availability_and_tiers(spec, source_epoch, timestamps)
    evidence_hashes = {
        source_file: file_hash(source_path),
        candidate["source_task_provenance"]["path"]: file_hash(test_path),
    }
    source_artifact_hashes = {
        "license": file_hash(license_path),
        "source_file": evidence_hashes[source_file],
        "source_implementation": hashlib.sha256(implementation.encode()).hexdigest(),
        "source_task": hashlib.sha256(
            candidate["source_task_description"].encode()
        ).hexdigest(),
        f"source_test:{candidate['source_task_provenance']['path']}": evidence_hashes[
            candidate["source_task_provenance"]["path"]
        ],
    }
    entry = {
        "source_id": candidate["source_id"],
        "source_tier_by_target": tiers,
        "repository_url": spec["repository_url"],
        "repository_commit": spec["commit"],
        "commit_timestamp": evidence["git"]["commit_timestamp"],
        "commit_timestamp_epoch": source_epoch,
        "license": {
            "spdx": spec["license_spdx"],
            "path": spec["license_path"],
            "sha256": file_hash(license_path),
        },
        "language": "python",
        "build_system": list(spec["build_system"]),
        "environment": environment,
        "source_task_description": candidate["source_task_description"],
        "source_task_provenance": candidate["source_task_provenance"],
        "source_file": source_file,
        "source_symbol": candidate["source_symbol"],
        "source_implementation_or_patch": implementation,
        "operation_class": candidate["operation_class"],
        "API_sequence": candidate["API_sequence"],
        "AST_signature": candidate["AST_signature"],
        "normalized_token_signature": candidate["normalized_token_signature"],
        "type_or_data_role_signature": candidate["type_or_data_role_signature"],
        "source_semantic_vector": candidate["source_semantic_vector"],
        "source_visible_libraries": candidate["source_visible_libraries"],
        "source_test_paths": [candidate["source_task_provenance"]["path"]],
        "source_test_command": ["/bin/bash", "-lc", f"cd /project && {logical_test}"],
        "source_test_result": "PASS",
        "source_build": build,
        "source_task_test": test,
        "focal_source_safety": {
            "classification": "PASS",
            "level": "C",
            "pstar": candidate["mechanical_pstar"],
            "evidence_command": [
                "/bin/bash",
                "-lc",
                f"cd /project && {logical_test}",
            ],
            "evidence_paths": [
                source_file,
                candidate["source_task_provenance"]["path"],
            ],
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
                spec["repository_url"],
                spec["name"],
            ],
            "fetch_command": [
                "git",
                "-C",
                spec["name"],
                "fetch",
                "--no-tags",
                "--depth=2",
                "origin",
                spec.get("anchor", spec["commit"]),
            ],
            "checkout_command": [
                "git",
                "-C",
                spec["name"],
                "checkout",
                "--detach",
                spec["commit"],
            ],
            "tree_sha256": evidence["tree"]["tree_sha256"],
            "file_count": evidence["tree"]["file_count"],
            "git_tree_object_sha1": evidence["git"]["git_tree_object_sha1"],
            "source_line_start": implementation_start,
            "source_line_end": implementation_end,
            "target_B_timestamps": timestamps,
            "strict_first_parent_of_anchor": spec.get("anchor"),
        },
    }
    validate_source_entry(entry, confirmatory=True)
    packet_audit = audit_memory_packet(render_memory_packet(entry), entry)
    if not (
        packet_audit["exact_implementation_identity"]
        and packet_audit["source_task_identity"]
        and not packet_audit["forbidden_target_or_oracle_material"]
        and not packet_audit["pstar_explanation_in_packet"]
    ):
        raise RuntimeError("new source packet fidelity failed")
    attempt["source_entry_sha256"] = stable_record_hash(entry)
    return entry, attempt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    output_root = args.output_root.absolute()
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite artifact root: {output_root}")
    cache = args.cache_root.resolve(strict=True)
    config_path = ROOT / "configs/v2/context-dependent-memory-source-corpus-development-v2.json"
    config = load_json(config_path)
    if config["successor_protocol_commit"] != SUCCESSOR_PROTOCOL_COMMIT:
        raise RuntimeError("source config does not name frozen successor protocol")

    started = time.monotonic()
    started_at = utc_now()
    ids = dataset_instance_ids()
    universe = source_universe_design(ids)
    partition = source_only_partition_assessment(
        load_json(FEASIBILITY_ROOT / "unseen-target-universe.json")["unseen_ids"]
    )
    specs = source_specifications(config, cache)
    specs_by_url = {spec["repository_url"]: spec for spec in specs}
    materializations = validate_materializations(specs, universe)
    discovery_rows = []
    discovery_seconds = 0.0
    for spec in specs:
        discovery_started = time.monotonic()
        discovery = discover_source_candidates(
            spec["source_tree"],
            repository_url=spec["repository_url"],
            repository_commit=spec["commit"],
            tier=spec["tier"],
        )
        elapsed = time.monotonic() - discovery_started
        discovery_seconds += elapsed
        discovery["runtime_seconds"] = round(elapsed, 6)
        if spec["tier"] == "S2":
            discovery["repository_order_sha256"] = materializations[spec["name"]][
                "git"
            ]["repository_order_sha256"]
        discovery_rows.append(discovery)

    queue = round_robin_candidates(discovery_rows)
    inherited_manifest = load_json(V1_ARTIFACT_ROOT / "source-corpus-manifest.json")
    inherited = inherited_manifest["entries"]
    if len(inherited) != INHERITED_V1_ENTRIES:
        raise RuntimeError("inherited V1 source count changed")
    for entry in inherited:
        validate_source_entry(entry, confirmatory=True)
        audit_memory_packet(render_memory_packet(entry), entry)
    inherited_impl_hashes = {
        hashlib.sha256(entry["source_implementation_or_patch"].encode()).hexdigest()
        for entry in inherited
    }
    timestamps = target_timestamps()
    new_entries: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    deterministic_exclusions: list[dict[str, Any]] = []
    size_decision = None
    selected_target = 50
    qualification_runtime = 0.0
    for candidate in queue:
        if len(attempts) >= NEW_CANDIDATE_ATTEMPT_CAP:
            break
        if candidate["source_implementation_sha256"] in inherited_impl_hashes:
            deterministic_exclusions.append(
                {
                    "source_id": candidate["source_id"],
                    "candidate_identity_sha256": candidate["candidate_identity_sha256"],
                    "reason": "INHERITED_IMPLEMENTATION_DUPLICATE",
                    "attempted": False,
                }
            )
            continue
        spec = specs_by_url[candidate["repository_url"]]
        attempt_started = time.monotonic()
        entry, attempt = qualify_candidate(
            candidate,
            spec,
            materializations[spec["name"]],
            timestamps,
        )
        elapsed = time.monotonic() - attempt_started
        qualification_runtime += elapsed
        attempt["end_to_end_attempt_runtime_seconds"] = round(elapsed, 6)
        attempt["attempt_number"] = len(attempts) + 1
        attempts.append(attempt)
        if entry is not None:
            new_entries.append(entry)
            inherited_impl_hashes.add(candidate["source_implementation_sha256"])
        if len(attempts) == PILOT_NEW_ATTEMPTS:
            materialization_bytes = sum(
                path.stat().st_size
                for spec_value in specs
                for path in Path(spec_value["source_tree"]).rglob("*")
                if path.is_file()
            )
            size_decision = choose_corpus_target(
                pilot_total_wall_seconds=discovery_seconds + qualification_runtime,
                pilot_qualified_count=len(new_entries),
                materialization_gib=materialization_bytes / (1024**3),
            )
            selected_target = size_decision["selected_target"]
        if len(inherited) + len(new_entries) >= selected_target and size_decision:
            break
    if size_decision is None:
        raise RuntimeError("candidate queue ended before the 10-attempt cost pilot")

    entries = [*inherited, *new_entries]
    if len(entries) < selected_target:
        raise RuntimeError(
            f"qualified corpus did not reach frozen target: {len(entries)} < {selected_target}"
        )
    if len({entry["source_id"] for entry in entries}) != len(entries):
        raise RuntimeError("expanded source IDs are not unique")
    breadth_input = [
        {
            "repository_url": entry["repository_url"],
            "source_tier": (
                "S2"
                if entry["repository_url"]
                in {spec["repository_url"] for spec in S2_SPECS}
                else "S1"
            ),
            "operation_class": entry["operation_class"],
        }
        for entry in entries
    ]
    breadth = corpus_breadth(breadth_input)
    if not breadth["pass"]:
        raise RuntimeError(f"expanded corpus breadth failed: {breadth}")
    corpus_hash = corpus_manifest_hash(entries)
    finished_at = utc_now()
    total_runtime = time.monotonic() - started

    universe["partition_assessment"] = partition
    universe["materialized_s2_queue_prefix"] = [
        {
            "repository_url": spec["repository_url"],
            "anchor_commit": spec["anchor"],
            "strict_parent_commit": spec["commit"],
            "qualification_environment_dependencies": spec["dependency_install"],
        }
        for spec in S2_SPECS
    ]
    universe["materializations"] = materializations
    manifest = {
        "schema": "cmpilot-expanded-source-corpus-manifest-v2",
        "status": "DEVELOPMENT_V2_VALIDATED_FROZEN_CANDIDATE",
        "development_only": True,
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "generated_at_utc": finished_at,
        "source_spec_path": config_path.relative_to(ROOT).as_posix(),
        "source_spec_sha256": sha256_file(config_path),
        "inherited_v1_manifest_sha256": sha256_file(
            V1_ARTIFACT_ROOT / "source-corpus-manifest.json"
        ),
        "inherited_v1_entries": len(inherited),
        "new_v2_entries": len(new_entries),
        "source_corpus_entries": len(entries),
        "selected_target": selected_target,
        "source_corpus_sha256": corpus_hash,
        "source_corpus_reproducible": True,
        "source_only_partition_used": False,
        "arbitrary_live_search_used": False,
        "s3_enabled": False,
        "breadth": breadth,
        "entries": entries,
    }
    validation = {
        "schema": "cmpilot-source-validation-summary-v2",
        "development_only": True,
        "source_corpus_sha256": corpus_hash,
        "source_corpus_entries": len(entries),
        "source_build_pass_count": sum(
            entry["source_build"]["classification"] == "PASS" for entry in entries
        ),
        "source_task_test_pass_count": sum(
            entry["source_task_test"]["classification"] == "PASS" for entry in entries
        ),
        "source_focal_safe_count": sum(
            entry["focal_source_safety"]["classification"] == "PASS"
            and entry["focal_source_safety"]["level"] in {"A", "B", "C"}
            for entry in entries
        ),
        "inherited_records_revalidated_without_mutation": len(inherited),
        "new_candidate_attempt_count": len(attempts),
        "new_qualified_count": len(new_entries),
        "new_attrition_count": sum(
            attempt["classification"] == "ATTRITION" for attempt in attempts
        ),
        "attempts": attempts,
        "deterministic_pre_attempt_exclusions": deterministic_exclusions,
        "all_commands_and_outputs_retained": True,
        "evaluated_model_inference": False,
    }
    discovery_summary = {
        "schema": "cmpilot-source-discovery-summary-v2",
        "protocol_id": PROTOCOL_ID,
        "candidate_generation_uses_target": False,
        "candidate_generation_uses_oracle": False,
        "candidate_generation_uses_model": False,
        "queue_sha256": stable_record_hash(queue),
        "queue_count": len(queue),
        "discoveries": discovery_rows,
    }
    runtime = {
        "schema": "cmpilot-source-corpus-runtime-v2",
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "discovery_runtime_seconds": round(discovery_seconds, 6),
        "qualification_runtime_seconds": round(qualification_runtime, 6),
        "total_runtime_seconds": round(total_runtime, 6),
        "attempted_new_candidates": len(attempts),
        "qualified_new_candidates": len(new_entries),
    }

    output_root.mkdir(parents=True)
    write_json(output_root / "source-universe-design.json", universe)
    write_json(output_root / "expanded-source-corpus-manifest.json", manifest)
    write_json(output_root / "source-validation-summary.json", validation)
    write_json(output_root / "source-discovery-summary.json", discovery_summary)
    write_json(output_root / "source-corpus-size-decision.json", size_decision)
    write_json(output_root / "source-corpus-runtime.json", runtime)
    shutil.copyfile(
        ROOT / "protocols/context-dependent-memory-source-pairing-development-v2.md",
        output_root / "successor-protocol.md",
    )
    shutil.copyfile(
        ROOT / "protocols/context-dependent-memory-source-pairing-development-v2.json",
        output_root / "successor-protocol.json",
    )
    print(
        json.dumps(
            {
                "entries": len(entries),
                "source_correct": validation["source_task_test_pass_count"],
                "source_focal_safe": validation["source_focal_safe_count"],
                "attempts": len(attempts),
                "attrition": validation["new_attrition_count"],
                "breadth": breadth["pass"],
                "corpus_sha256": corpus_hash,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

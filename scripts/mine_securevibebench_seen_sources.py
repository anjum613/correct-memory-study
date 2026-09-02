#!/usr/bin/env python3
"""Mine pre-B source evidence for only the declared SecureVibeBench seen set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from cmpilot.securevibebench_development import (
    guard_instance_access,
    load_seen_ids,
    procedure_representation,
    procedure_similarity,
)


CODE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp"}
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{7,}")


def git(repo: Path, *args: str, check: bool = True, timeout: int = 60) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return (exc.stdout or b"") + b"\n[COMMAND_TIMEOUT]\n"
    if check and result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def added_text(diff: bytes) -> str:
    lines = []
    for line in diff.decode(errors="replace").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line[1:])
    return "\n".join(lines)


def distinctive_identifier(source: str) -> str | None:
    values = sorted(set(IDENTIFIER.findall(source)), key=lambda value: (-len(value), value))
    return values[0] if values else None


def command_record(argv: list[str], output: bytes) -> dict[str, Any]:
    return {
        "argv": argv,
        "output_sha256": sha256(output),
        "output_size_bytes": len(output),
        "first_lines": output.decode(errors="replace").splitlines()[:5],
        "timeout": b"[COMMAND_TIMEOUT]" in output,
    }


def source_files(repo: Path, commit: str) -> list[str]:
    values = git(repo, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    return [value for value in values if Path(value).suffix.lower() in CODE_SUFFIXES]


def mine_case(instance_id: str, case: dict[str, Any], projects: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    repo = projects / case["repo_name"]
    b, u = case["B"], case["U"]
    b_time = int(git(repo, "show", "-s", "--format=%ct", b).strip())
    diff = git(repo, "diff", "--binary", b, u)
    target_text = added_text(diff)
    target_representation = procedure_representation(target_text)
    changed = git(repo, "diff", "--name-only", b, u).decode().splitlines()
    code_paths = [path for path in changed if Path(path).suffix.lower() in CODE_SUFFIXES]
    paths: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for path in code_paths:
        follow_argv = ["git", "log", "--follow", "--format=%H%x09%ct%x09%s", b, "--", path]
        follow = git(repo, *follow_argv[1:], timeout=10)
        blame_argv = ["git", "blame", "-M", "-C", "-C", b, "--", path]
        blame = git(repo, *blame_argv[1:], timeout=10)
        needle = distinctive_identifier(target_text)
        pickaxe = b""
        regex_log = b""
        pickaxe_argv: list[str] | None = None
        regex_argv: list[str] | None = None
        if needle:
            pickaxe_argv = ["git", "log", "--format=%H%x09%ct%x09%s", f"-S{needle}", f"{b}^", "--", path]
            pickaxe = git(repo, *pickaxe_argv[1:], timeout=10)
            regex_argv = ["git", "log", "--format=%H%x09%ct%x09%s", f"-G{re.escape(needle)}", f"{b}^", "--", path]
            regex_log = git(repo, *regex_argv[1:], timeout=10)

        previous = git(repo, "log", "-1", "--format=%H%x09%ct", f"{b}^", "--", path).decode().strip()
        candidate = None
        if previous:
            commit, timestamp = previous.split("\t", 1)
            historical_diff = git(repo, "show", "--format=", "--unified=3", commit, "--", path)
            excerpt = added_text(historical_diff)
            similarity = procedure_similarity(target_representation, procedure_representation(excerpt))
            candidate = {
                "tier": "S2",
                "commit": commit,
                "commit_time": int(timestamp),
                "strictly_before_b_by_time": int(timestamp) < b_time,
                "ancestor_of_b": subprocess.run(
                    ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, b],
                    check=False,
                ).returncode
                == 0,
                "path": path,
                "excerpt_sha256": sha256(excerpt.encode()),
                "excerpt_size_bytes": len(excerpt.encode()),
                "similarity": similarity,
                "correctness_evidence": "not-established",
                "safety_evidence": "not-established",
                "trust_predicate": None,
            }
            candidates.append(candidate)

        paths.append(
            {
                "path": path,
                "needle": needle,
                "S1_pickaxe": command_record(pickaxe_argv or [], pickaxe),
                "S2_follow": command_record(follow_argv, follow),
                "blame_move_copy": command_record(blame_argv, blame),
                "S4_regex": command_record(regex_argv or [], regex_log),
                "candidate": candidate,
            }
        )

    unrelated_pool = [path for path in source_files(repo, b) if path not in code_paths]
    negative = None
    if unrelated_pool:
        chosen = min(unrelated_pool, key=lambda path: hashlib.sha256(f"{instance_id}|{path}".encode()).hexdigest())
        content = git(repo, "show", f"{b}:{chosen}").decode(errors="replace")[:8000]
        negative = {
            "path": chosen,
            "sampling_rule": "minimum SHA256(instance_id + '|' + path) over non-target C/C++ paths",
            "content_sha256": sha256(content.encode()),
            "similarity": procedure_similarity(target_representation, procedure_representation(content)),
        }

    eligible = [
        item
        for item in candidates
        if item["strictly_before_b_by_time"]
        and item["ancestor_of_b"]
        and item["correctness_evidence"] == "established"
        and item["safety_evidence"] == "established"
        and item["trust_predicate"]
    ]
    result = {
        "instance_id": instance_id,
        "duplicate_member_ids": case.get("duplicate_member_ids", [instance_id]),
        "repository": case["repo_name"],
        "B": b,
        "U": u,
        "B_commit_time": b_time,
        "target_added_text_sha256": sha256(target_text.encode()),
        "target_added_text_size_bytes": len(target_text.encode()),
        "changed_code_paths": code_paths,
        "search_tiers": {
            "S1": "exact pickaxe hits before B",
            "S2": "latest same-file historical change before B",
            "S3": {"sibling_files_enumerated": len(unrelated_pool), "selection": "not-promoted-without-function-provenance"},
            "S4": "regex/API diagnostic before B; no candidate promoted without p* evidence",
        },
        "path_evidence": paths,
        "candidate_count": len(candidates),
        "eligible_source_count": len(eligible),
        "selected_source": None,
        "selection_reason": "No candidate has machine evidence for source correctness, safety, and an explicit trust predicate p*.",
        "runtime_seconds": round(time.monotonic() - started, 3),
    }
    diagnostic = {
        "instance_id": instance_id,
        "candidate_target_scores": [item["similarity"] for item in candidates],
        "deterministic_unrelated_negative": negative,
    }
    return result, diagnostic


def main(args: argparse.Namespace) -> None:
    seen = load_seen_ids(args.seen_set)
    config = json.loads(args.case_config.read_text())["cases"]
    unique: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
    for instance_id in seen:
        guard_instance_access(instance_id, seen, implementation_access=True)
        case = dict(config[instance_id])
        key = (case["repo_name"], case["U"], case["R"])
        if key in unique:
            unique[key][1].setdefault("duplicate_member_ids", [unique[key][0]]).append(instance_id)
        else:
            case["duplicate_member_ids"] = [instance_id]
            unique[key] = (instance_id, case)

    results = []
    diagnostics = []
    for instance_id, case in unique.values():
        result, diagnostic = mine_case(instance_id, case, args.projects)
        results.append(result)
        diagnostics.append(diagnostic)

    retrieval = {
        "schema": "securevibebench-source-retrieval-v1",
        "seen_only_guard": True,
        "search_scope": "commit ancestry strictly before B in the same repository",
        "refactoring_miner": {
            "used": False,
            "reason": "RefactoringMiner targets Java/Kotlin refactorings; the six unique seen transformations are C/C++.",
        },
        "memory_extraction": {
            "status": "specified-not-instantiated",
            "format": "<SOURCE_TASK_CONTEXT>canonical source metadata</SOURCE_TASK_CONTEXT>\\n<SOURCE_IMPLEMENTATION>exact historical bytes</SOURCE_IMPLEMENTATION>",
            "future_information_fields_forbidden": ["CVE", "vulnerability description", "PoV", "R/VFC", "future commits", "security warning"],
        },
        "cases": results,
    }
    calibration = {
        "schema": "securevibebench-source-threshold-calibration-v1",
        "seen_only_guard": True,
        "representation": {
            "token_shingles": 5,
            "identifier_normalization": "first-occurrence ID numbering",
            "combined_score": "0.5*token_shingle_jaccard + 0.3*API_jaccard + 0.2*control_jaccard",
        },
        "diagnostics": diagnostics,
        "positive_structural_transformations_available": 0,
        "negative_samples": sum(item["deterministic_unrelated_negative"] is not None for item in diagnostics),
        "threshold_frozen": False,
        "recommended_threshold": None,
        "conclusion": "Insufficient labeled pre-B positive structural transformations; freezing a threshold would be outcome-driven.",
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "source-retrieval-results.json").write_text(json.dumps(retrieval, indent=2, sort_keys=True) + "\n")
    (args.output / "source-threshold-calibration.json").write_text(json.dumps(calibration, indent=2, sort_keys=True) + "\n")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--seen-set", required=True, type=Path)
    result.add_argument("--case-config", required=True, type=Path)
    result.add_argument("--projects", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    return result


if __name__ == "__main__":
    main(parser().parse_args())

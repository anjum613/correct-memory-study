#!/usr/bin/env python3
"""Materialize and screen the frozen V2 prospective candidate universe."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/v2-prospective-discovery"
PROTOCOL_PATH = ROOT / "protocols/v2-prospective-family-discovery-v1.json"
DEFAULT_SOURCE_ROOT = ROOT / ".cache/v2-prospective-discovery/sources"
DEFAULT_UPSTREAM_ROOT = ROOT / ".cache/v2-prospective-discovery/upstreams"
LEDGER_PATH = ARTIFACT_ROOT / "ordered-candidate-ledger.jsonl"
SOURCE_MANIFEST_PATH = ARTIFACT_ROOT / "source-dataset-manifest.json"
SCREENING_EVIDENCE_ROOT = ARTIFACT_ROOT / "screening-evidence"
STAGE_B_QUESTIONS = tuple(f"T{index}" for index in range(1, 9)) + ("H1",)
SEMANTIC_QUESTIONS = tuple(f"Q{index}" for index in range(1, 13))

SOURCE_LAYOUT = {
    "vcc-eval": {
        "metadata": ["dataset/tool_assisted_manual_dataset.json"],
        "protocol_name": "VCC-Eval",
    },
    "vul4j": {
        "metadata": ["dataset/vul4j_dataset.csv"],
        "protocol_name": "Vul4J",
    },
    "vulnloc": {
        "metadata": [],
        "protocol_name": "VulnLoc",
    },
    "secbench-js": {
        "metadata": [],
        "protocol_name": "SecBench.js",
    },
}

CVE_RE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,}", re.IGNORECASE)
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
GITHUB_COMMIT_RE = re.compile(
    r"https?://github\.com/([^/\s]+/[^/\s]+?)(?:\.git)?/commit/([0-9a-fA-F]{7,64})"
)
REPO_COMMENT_RE = re.compile(r"^# Repo\s*:\s*([^\s]+/[^\s]+)\s*$", re.MULTILINE)
LEX_RE = re.compile(
    r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|"
    r"[A-Za-z_$][A-Za-z0-9_$]*|0[xX][0-9A-Fa-f]+|[0-9]+(?:\.[0-9]+)?|[^\s]",
    re.DOTALL,
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
NUMBER_RE = re.compile(r"^(?:0[xX][0-9A-Fa-f]+|[0-9]+(?:\.[0-9]+)?)$")
CONTROL_CALL_WORDS = {"if", "for", "while", "switch", "catch", "return", "throw", "new", "synchronized"}
EXECUTABLE_EXTENSIONS = {
    ".java", ".kt", ".kts", ".scala", ".groovy", ".js", ".cjs", ".mjs",
    ".ts", ".tsx", ".py", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp",
    ".go", ".rs", ".rb", ".php", ".cs", ".sh",
}
EXCLUDED_TOP_LEVEL_PATHS = {"doc", "docs", "documentation", "test", "tests", "testing", "example", "examples"}
EXCLUDED_ANY_PATH_PARTS = {"fixture", "fixtures", "vendor", "vendored", "generated", "benchmark", "benchmarks"}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalize_repository(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.strip().lower().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.startswith("git@github.com:"):
        normalized = "https://github.com/" + normalized.removeprefix("git@github.com:")
    return normalized


def normalize_cve(value: str | None) -> str | None:
    if not value:
        return None
    match = CVE_RE.search(value.upper())
    return match.group(0) if match else None


def commit_from_url(value: str | None) -> str | None:
    if not value:
        return None
    match = GITHUB_COMMIT_RE.search(value)
    return match.group(2).lower() if match else None


def repository_from_commit_url(value: str | None) -> str:
    if not value:
        return ""
    match = GITHUB_COMMIT_RE.search(value)
    return normalize_repository(f"https://github.com/{match.group(1)}") if match else ""


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        errors="replace" if text else None,
    )
    return result.stdout


def run_git(repo: Path, *args: str) -> dict[str, Any]:
    command = ["git", "-C", str(repo), *args]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def git_blob(repo: Path, path: str) -> bytes:
    return git(repo, "show", f"HEAD:{path}", text=False)  # type: ignore[return-value]


def git_names(repo: Path) -> list[str]:
    output = git(repo, "ls-tree", "-r", "--name-only", "HEAD")
    return str(output).splitlines()


@dataclass(frozen=True)
class Candidate:
    source_tier: str
    dataset_entry: str
    cve: str | None
    repository: str
    intro: str | None
    fix: str | None
    dataset_ordinal: int
    metadata: dict[str, Any]

    @property
    def dedupe_key(self) -> tuple[str, str, str] | None:
        if not self.repository or not self.intro or not self.fix:
            return None
        return (self.repository, self.intro, self.fix)

    @property
    def sort_key(self) -> tuple[Any, ...]:
        identifier = self.cve or f"~{self.dataset_entry.lower()}"
        return (
            identifier,
            self.repository or "~",
            self.intro or "~",
            self.fix or "~",
            self.dataset_entry.lower(),
            self.dataset_ordinal,
        )


def parse_vcc(raw: bytes) -> list[dict[str, Any]]:
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("VCC-Eval dataset root must be a list")
    return value


def parse_vul4j(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def materialize_primary(vcc_raw: bytes, vul4j_raw: bytes) -> tuple[list[Candidate], set[int]]:
    vcc_rows = parse_vcc(vcc_raw)
    vul4j_rows = parse_vul4j(vul4j_raw)
    intersection: dict[tuple[str, str], list[dict[str, str]]] = {}
    for ordinal, row in enumerate(vul4j_rows, start=1):
        cve = normalize_cve(row.get("cve_id"))
        repo = normalize_repository(f"https://github.com/{row.get('repo_slug', '')}")
        if cve and repo:
            enriched = dict(row)
            enriched["_ordinal"] = str(ordinal)
            intersection.setdefault((cve, repo), []).append(enriched)

    candidates: list[Candidate] = []
    matched_vul4j_ordinals: set[int] = set()
    for vcc_ordinal, row in enumerate(vcc_rows, start=1):
        cve = normalize_cve(row.get("cve"))
        repo = normalize_repository(row.get("repository"))
        matches = intersection.get((cve or "", repo), [])
        tier = "TIER_1_VCC_EVAL_INTERSECTION_VUL4J" if matches else "TIER_2_REMAINING_VCC_EVAL_WITH_UPSTREAM_WITNESS_GATE"
        match_ids = sorted(item["vul_id"] for item in matches)
        matched_vul4j_ordinals.update(int(item["_ordinal"]) for item in matches)
        fixing = row.get("fixing") or []
        if not isinstance(fixing, list):
            fixing = [fixing]
        for fix_index, fix in enumerate(fixing, start=1):
            entry = f"VCC-Eval:{vcc_ordinal}:fix-{fix_index}"
            if match_ids:
                entry += "|" + ",".join(match_ids)
            candidates.append(
                Candidate(
                    source_tier=tier,
                    dataset_entry=entry,
                    cve=cve,
                    repository=repo,
                    intro=str(row.get("introducing") or "").lower() or None,
                    fix=str(fix or "").lower() or None,
                    dataset_ordinal=vcc_ordinal,
                    metadata={
                        "vcc_cwe": row.get("cwe"),
                        "vcc_intro_lines": row.get("introducing_lines", {}),
                        "vcc_fixing_lines": row.get("fixing_lines", {}),
                        "vul4j_ids": match_ids,
                    },
                )
            )

    for ordinal, row in enumerate(vul4j_rows, start=1):
        if ordinal in matched_vul4j_ordinals:
            continue
        patch_url = row.get("human_patch")
        candidates.append(
            Candidate(
                source_tier="TIER_3_REMAINING_VUL4J_WITH_INDEPENDENT_EXACT_INTRO_GATE",
                dataset_entry=str(row.get("vul_id") or f"Vul4J:{ordinal}"),
                cve=normalize_cve(row.get("cve_id")),
                repository=normalize_repository(
                    repository_from_commit_url(patch_url)
                    or f"https://github.com/{row.get('repo_slug', '')}"
                ),
                intro=None,
                fix=commit_from_url(patch_url),
                dataset_ordinal=ordinal,
                metadata={
                    "vul4j_cve_id": row.get("cve_id"),
                    "vul4j_cwe_id": row.get("cwe_id"),
                    "human_patch_url": patch_url,
                    "build_system": row.get("build_system"),
                    "compile_cmd": row.get("compile_cmd"),
                    "test_cmd": row.get("test_cmd"),
                    "failing_tests": row.get("failing_tests"),
                },
            )
        )
    return candidates, matched_vul4j_ordinals


def materialize_vulnloc(repo: Path) -> list[Candidate]:
    readmes = [
        name
        for name in git_names(repo)
        if name.startswith("data/") and name.endswith("/README.txt") and name.count("/") == 3
    ]
    candidates: list[Candidate] = []
    for ordinal, path in enumerate(sorted(readmes), start=1):
        raw = git_blob(repo, path)
        text = raw.decode("utf-8", errors="replace")
        match = GITHUB_COMMIT_RE.search(text)
        native_id = path.split("/")[2]
        candidates.append(
            Candidate(
                source_tier="TIER_4A_VULNLOC",
                dataset_entry=f"VulnLoc:{path}",
                cve=normalize_cve(native_id.replace("_", "-")),
                repository=(
                    normalize_repository(f"https://github.com/{match.group(1)}") if match else ""
                ),
                intro=None,
                fix=match.group(2).lower() if match else None,
                dataset_ordinal=ordinal,
                metadata={"readme_path": path, "readme_sha256": sha256_bytes(raw)},
            )
        )
    return candidates


def materialize_secbench(repo: Path) -> list[Candidate]:
    names = set(git_names(repo))
    package_paths = sorted(
        name
        for name in names
        if name.endswith("/package.json")
        and name.count("/") == 2
        and f"{name.rsplit('/', 1)[0]}/Dockerfile" in names
    )
    candidates: list[Candidate] = []
    for ordinal, package_path in enumerate(package_paths, start=1):
        directory = package_path.rsplit("/", 1)[0]
        package_raw = git_blob(repo, package_path)
        docker_raw = git_blob(repo, f"{directory}/Dockerfile")
        package = json.loads(package_raw)
        docker = docker_raw.decode("utf-8", errors="replace")
        repo_match = REPO_COMMENT_RE.search(docker)
        repository = (
            normalize_repository(f"https://github.com/{repo_match.group(1)}") if repo_match else ""
        )
        fix_value = str(package.get("fixCommit") or "")
        fix = fix_value.lower() if COMMIT_RE.fullmatch(fix_value) else None
        candidates.append(
            Candidate(
                source_tier="TIER_4B_SECBENCH_JS",
                dataset_entry=f"SecBench.js:{directory}",
                cve=normalize_cve(str(package.get("id") or "")),
                repository=repository,
                intro=None,
                fix=fix,
                dataset_ordinal=ordinal,
                metadata={
                    "native_id": package.get("id"),
                    "benchmark_path": directory,
                    "fixed_version": package.get("fixedVersion"),
                    "package_json_sha256": sha256_bytes(package_raw),
                    "dockerfile_sha256": sha256_bytes(docker_raw),
                },
            )
        )
    return candidates


def ordered_universe(source_root: Path) -> list[Candidate]:
    primary, _ = materialize_primary(
        git_blob(source_root / "vcc-eval", SOURCE_LAYOUT["vcc-eval"]["metadata"][0]),
        git_blob(source_root / "vul4j", SOURCE_LAYOUT["vul4j"]["metadata"][0]),
    )
    all_candidates = primary + materialize_vulnloc(source_root / "vulnloc") + materialize_secbench(source_root / "secbench-js")
    tier_order = {
        "TIER_1_VCC_EVAL_INTERSECTION_VUL4J": 1,
        "TIER_2_REMAINING_VCC_EVAL_WITH_UPSTREAM_WITNESS_GATE": 2,
        "TIER_3_REMAINING_VUL4J_WITH_INDEPENDENT_EXACT_INTRO_GATE": 3,
        "TIER_4A_VULNLOC": 4,
        "TIER_4B_SECBENCH_JS": 5,
    }
    seen: set[tuple[str, str, str]] = set()
    deduplicated: list[Candidate] = []
    for candidate in sorted(all_candidates, key=lambda item: (tier_order[item.source_tier], item.sort_key)):
        key = candidate.dedupe_key
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        deduplicated.append(candidate)
    return deduplicated


def candidate_record(candidate: Candidate, position: int) -> dict[str, Any]:
    return {
        "event_type": "CANDIDATE_REGISTERED",
        "position": position,
        "source_tier": candidate.source_tier,
        "dataset_entry": candidate.dataset_entry,
        "CVE": candidate.cve,
        "repository": candidate.repository or None,
        "B": None,
        "INTRO/U": candidate.intro,
        "FIX/R": candidate.fix,
        "build_status": "NOT_SCREENED",
        "task_identifiability": "NOT_SCREENED",
        "source_analogue_count": 0,
        "source_S": None,
        "trust_predicate_status": "NOT_SCREENED",
        "memory_status": "NOT_SCREENED",
        "security_witness_status": "NOT_SCREENED",
        "control_matrix_status": "NOT_SCREENED",
        "final_decision": "NOT_SCREENED",
        "rejection_reason": None,
        "evidence_hashes": {},
        "stage_statuses": {"A": "NOT_SCREENED", "B": "NOT_SCREENED", "C": "NOT_SCREENED"},
        "dataset_ordinal": candidate.dataset_ordinal,
        "source_metadata": candidate.metadata,
    }


def source_manifest(source_root: Path, protocol: dict[str, Any], ledger_bytes: bytes) -> dict[str, Any]:
    sources = []
    by_name = {item["name"]: item for item in protocol["sources"]}
    for directory, layout in SOURCE_LAYOUT.items():
        repo = source_root / directory
        source = by_name[layout["protocol_name"]]
        commit = str(git(repo, "rev-parse", "HEAD")).strip()
        tree = str(git(repo, "rev-parse", "HEAD^{tree}")).strip()
        if commit != source["commit"] or tree != source["root_tree"]:
            raise ValueError(f"frozen source mismatch for {directory}")
        metadata = []
        for path in layout["metadata"]:
            raw = git_blob(repo, path)
            metadata.append({"path": path, "bytes": len(raw), "sha256": sha256_bytes(raw)})
        sources.append({**source, "local_directory": directory, "metadata_files": metadata})
    return {
        "schema": "v2-prospective-source-dataset-manifest-v1",
        "protocol_sha256": sha256_bytes(PROTOCOL_PATH.read_bytes()),
        "sources": sources,
        "initial_registration_ledger_sha256": sha256_bytes(ledger_bytes),
        "initial_registration_ledger_bytes": len(ledger_bytes),
        "tool_versions": {
            "python": sys.version.split()[0],
            "git": subprocess.run(["git", "--version"], check=True, capture_output=True, text=True).stdout.strip(),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def materialize(source_root: Path, ledger_path: Path, manifest_path: Path) -> dict[str, Any]:
    if ledger_path.exists() or manifest_path.exists():
        raise FileExistsError("refusing to overwrite frozen ledger or source manifest")
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    candidates = ordered_universe(source_root)
    records = [candidate_record(candidate, position) for position, candidate in enumerate(candidates, start=1)]
    ledger_bytes = ("".join(canonical_json(row) + "\n" for row in records)).encode("utf-8")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_bytes(ledger_bytes)
    manifest = source_manifest(source_root, protocol, ledger_bytes)
    counts: dict[str, int] = {}
    for row in records:
        counts[row["source_tier"]] = counts.get(row["source_tier"], 0) + 1
    manifest["candidate_universe_size"] = len(records)
    manifest["candidate_counts_by_tier"] = counts
    write_json(manifest_path, manifest)
    return {"candidate_universe_size": len(records), "candidate_counts_by_tier": counts}


def validate_registration_ledger(ledger_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger_bytes = ledger_path.read_bytes()
    prefix_size = manifest["initial_registration_ledger_bytes"]
    prefix = ledger_bytes[:prefix_size]
    if sha256_bytes(prefix) != manifest["initial_registration_ledger_sha256"]:
        raise ValueError("initial candidate registration prefix hash mismatch")
    records = [json.loads(line) for line in prefix.decode("utf-8").splitlines()]
    expected_count = manifest["candidate_universe_size"]
    if len(records) != expected_count:
        raise ValueError("candidate registration count mismatch")
    if [row["position"] for row in records] != list(range(1, expected_count + 1)):
        raise ValueError("candidate positions are not contiguous")
    if any(row["event_type"] != "CANDIDATE_REGISTERED" for row in records):
        raise ValueError("non-registration event found in immutable prefix")
    if any(row["final_decision"] != "NOT_SCREENED" for row in records):
        raise ValueError("screening outcome found in immutable registration prefix")
    actual_counts: dict[str, int] = {}
    for row in records:
        tier = row["source_tier"]
        actual_counts[tier] = actual_counts.get(tier, 0) + 1
    if actual_counts != manifest["candidate_counts_by_tier"]:
        raise ValueError("candidate tier counts mismatch")
    return {
        "candidate_universe_size": expected_count,
        "candidate_counts_by_tier": actual_counts,
        "append_bytes": len(ledger_bytes) - prefix_size,
    }


def registration_records(ledger_path: Path, manifest_path: Path) -> list[dict[str, Any]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prefix = ledger_path.read_bytes()[: manifest["initial_registration_ledger_bytes"]]
    return [json.loads(line) for line in prefix.decode("utf-8").splitlines()]


def upstream_cache_path(repository: str, upstream_root: Path) -> Path:
    slug = repository.removeprefix("https://github.com/").replace("/", "__")
    return upstream_root / f"{slug}.git"


def is_production_executable(path: str) -> bool:
    parts = Path(path).parts
    directories = tuple(part.lower() for part in parts[:-1])
    excluded = (
        (directories and directories[0] in EXCLUDED_TOP_LEVEL_PATHS)
        or bool(set(directories) & EXCLUDED_ANY_PATH_PARTS)
        or any(pair in {("src", "test"), ("src", "tests")} for pair in zip(directories, directories[1:]))
    )
    return Path(path).suffix.lower() in EXECUTABLE_EXTENSIONS and not excluded


def static_screen_record(row: dict[str, Any], upstream_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    position = row["position"]
    repository = row["repository"]
    intro = row["INTRO/U"]
    fix = row["FIX/R"]
    evidence: dict[str, Any] = {
        "schema": "v2-prospective-stage-a-static-evidence-v1",
        "position": position,
        "repository": repository,
        "INTRO/U": intro,
        "FIX/R": fix,
        "gates": {},
        "commands": [],
    }
    failure: str | None = None
    parent: str | None = None

    if not repository or not intro or not fix:
        failure = "REJECT_A1_MISSING_REPOSITORY_INTRO_OR_FIX"
        evidence["gates"]["A1"] = {"status": "FAIL", "reason": failure}
    else:
        repo = upstream_cache_path(repository, upstream_root)
        remote_check = run_git(repo, "config", "--get", "remote.origin.url") if repo.is_dir() else None
        a2_pass = bool(remote_check and remote_check["returncode"] == 0)
        evidence["gates"]["A2"] = {
            "status": "PASS" if a2_pass else "FAIL",
            "cache_path": repo.relative_to(ROOT).as_posix() if repo.is_relative_to(ROOT) else str(repo),
            "remote": remote_check,
        }
        if not a2_pass:
            failure = "REJECT_A2_UPSTREAM_NOT_RECONSTRUCTIBLE"
        else:
            type_results = {revision: run_git(repo, "cat-file", "-t", revision) for revision in (intro, fix)}
            evidence["commands"].extend(type_results.values())
            a1_pass = all(
                result["returncode"] == 0 and result["stdout"].strip() == "commit"
                for result in type_results.values()
            )
            evidence["gates"]["A1"] = {"status": "PASS" if a1_pass else "FAIL", "objects": type_results}
            if not a1_pass:
                failure = "REJECT_A1_COMMIT_OBJECT_MISSING"
            else:
                ancestor = run_git(repo, "merge-base", "--is-ancestor", intro, fix)
                evidence["commands"].append(ancestor)
                evidence["gates"]["A3"] = {"status": "PASS" if ancestor["returncode"] == 0 else "FAIL", "result": ancestor}
                if ancestor["returncode"] != 0:
                    failure = "REJECT_A3_INTRO_NOT_ANCESTOR_OF_FIX"
                parents_result = run_git(repo, "show", "-s", "--format=%P", intro)
                evidence["commands"].append(parents_result)
                parents = parents_result["stdout"].strip().split()
                if len(parents) == 1:
                    parent = parents[0]
                evidence["gates"]["A4"] = {
                    "status": "PASS" if parent else "FAIL",
                    "parents": parents,
                    "documented_pre_state": None,
                }
                if failure is None and parent is None:
                    failure = "REJECT_A4_INTRO_NOT_SINGLE_PARENT"

                diff_result = run_git(repo, "diff-tree", "--no-commit-id", "--numstat", "-r", f"{intro}^", intro)
                evidence["commands"].append(diff_result)
                changed: list[dict[str, Any]] = []
                for line in diff_result["stdout"].splitlines():
                    fields = line.split("\t", 2)
                    if len(fields) != 3:
                        continue
                    added, deleted, path = fields
                    changed.append(
                        {
                            "path": path,
                            "added": int(added) if added.isdigit() else None,
                            "deleted": int(deleted) if deleted.isdigit() else None,
                            "production_executable": is_production_executable(path),
                        }
                    )
                executable = [item for item in changed if item["production_executable"]]
                a8_pass = diff_result["returncode"] == 0 and bool(executable)
                evidence["gates"]["A8"] = {"status": "PASS" if a8_pass else "FAIL", "changed_paths": changed, "qualifying_paths": executable}
                if failure is None and not a8_pass:
                    failure = "REJECT_A8_NO_EXECUTABLE_CODE_CHANGE"

                message_result = run_git(repo, "show", "-s", "--format=%s%n%b", intro)
                evidence["commands"].append(message_result)
                added_executable_lines = sum(item["added"] or 0 for item in executable)
                a9_pass = bool(message_result["stdout"].strip()) and added_executable_lines > 0
                evidence["gates"]["A9"] = {
                    "status": "PASS" if a9_pass else "FAIL",
                    "commit_message": message_result["stdout"],
                    "added_executable_lines": added_executable_lines,
                }
                if failure is None and not a9_pass:
                    failure = "REJECT_A9_NO_POTENTIALLY_DISTINGUISHABLE_FUNCTIONAL_CHANGE"

    evidence["static_decision"] = "REJECTED" if failure else "PASS_PENDING_STAGE_B"
    evidence["rejection_reason"] = failure
    evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
    event = dict(row)
    event.update(
        {
            "event_type": "STAGE_A_STATIC_RESULT",
            "B": parent,
            "build_status": "NOT_RUN_EARLY_STATIC",
            "final_decision": "REJECTED" if failure else "PENDING_STAGE_B",
            "rejection_reason": failure,
            "stage_statuses": {
                "A": "FAIL" if failure else "STATIC_PASS_DYNAMIC_DEFERRED",
                "B": "NOT_SCREENED",
                "C": "NOT_SCREENED",
            },
            "evidence_hashes": {"stage_a_static": sha256_bytes(evidence_bytes)},
        }
    )
    return event, evidence


def screen_static(
    ledger_path: Path,
    manifest_path: Path,
    upstream_root: Path,
    evidence_root: Path,
    start: int,
    end: int,
) -> dict[str, Any]:
    validation = validate_registration_ledger(ledger_path, manifest_path)
    if validation["append_bytes"] != 0:
        raise ValueError("static screening requires a registration-only ledger")
    rows = registration_records(ledger_path, manifest_path)
    selected = [row for row in rows if start <= row["position"] <= end]
    if [row["position"] for row in selected] != list(range(start, end + 1)):
        raise ValueError("requested screening range is not contiguous in candidate ledger")
    events: list[dict[str, Any]] = []
    for row in selected:
        event, evidence = static_screen_record(row, upstream_root)
        evidence_bytes = (json.dumps(evidence, indent=2, sort_keys=True) + "\n").encode("utf-8")
        evidence_path = evidence_root / f"position-{row['position']:04d}" / "stage-a-static.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        if evidence_path.exists():
            raise FileExistsError(f"refusing to overwrite {evidence_path}")
        evidence_path.write_bytes(evidence_bytes)
        events.append(event)
    with ledger_path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(canonical_json(event) + "\n")
    rejected = sum(event["final_decision"] == "REJECTED" for event in events)
    return {"screened": len(events), "rejected": rejected, "pending_stage_b": len(events) - rejected}


def ledger_events(ledger_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]


def validate_stage_b_form(value: dict[str, Any], expected_position: int) -> None:
    if value.get("schema") != "v2-prospective-stage-b-task-review-v1":
        raise ValueError("invalid Stage B form schema")
    if value.get("position") != expected_position:
        raise ValueError("Stage B form position mismatch")
    answers = value.get("answers")
    if not isinstance(answers, dict) or tuple(answers) != STAGE_B_QUESTIONS:
        raise ValueError("Stage B form must contain T1-T8 and H1 in order")
    for key, answer in answers.items():
        if answer.get("answer") not in {"YES", "NO"}:
            raise ValueError(f"invalid answer for {key}")
        if not answer.get("evidence"):
            raise ValueError(f"missing evidence for {key}")
    all_yes = all(answer["answer"] == "YES" for answer in answers.values())
    expected_decision = "PASS_STATIC_IDENTIFIABLE_PENDING_EXECUTION" if all_yes else "REJECTED"
    if value.get("decision") != expected_decision:
        raise ValueError("Stage B decision does not follow unanimous rule")
    if all_yes and value.get("rejection_reason") is not None:
        raise ValueError("passing Stage B form has rejection reason")
    if not all_yes and not value.get("rejection_reason"):
        raise ValueError("rejected Stage B form lacks rejection reason")


def record_stage_b(
    ledger_path: Path,
    manifest_path: Path,
    evidence_root: Path,
    start: int,
    end: int,
) -> dict[str, Any]:
    validate_registration_ledger(ledger_path, manifest_path)
    events = ledger_events(ledger_path)
    existing_stage_b = {event["position"] for event in events if event["event_type"] == "STAGE_B_RESULT"}
    if existing_stage_b & set(range(start, end + 1)):
        raise ValueError("refusing to append duplicate Stage B event")
    latest: dict[int, dict[str, Any]] = {}
    for event in events:
        latest[event["position"]] = event
    output: list[dict[str, Any]] = []
    for position in range(start, end + 1):
        prior = latest.get(position)
        if not prior or prior["event_type"] != "STAGE_A_STATIC_RESULT":
            raise ValueError(f"position {position} lacks Stage A static result")
        if prior["final_decision"] == "REJECTED":
            continue
        form_path = evidence_root / f"position-{position:04d}" / "stage-b-task-identifiability.json"
        form = json.loads(form_path.read_text(encoding="utf-8"))
        validate_stage_b_form(form, position)
        form_sha = sha256_bytes(form_path.read_bytes())
        passed = form["decision"] == "PASS_STATIC_IDENTIFIABLE_PENDING_EXECUTION"
        event = dict(prior)
        hashes = dict(prior["evidence_hashes"])
        hashes["stage_b_task_identifiability"] = form_sha
        event.update(
            {
                "event_type": "STAGE_B_RESULT",
                "task_identifiability": form["decision"],
                "final_decision": "PENDING_STAGE_C" if passed else "REJECTED",
                "rejection_reason": form["rejection_reason"],
                "stage_statuses": {
                    "A": prior["stage_statuses"]["A"],
                    "B": "STATIC_PASS_EXECUTION_DEFERRED" if passed else "FAIL",
                    "C": "NOT_SCREENED",
                },
                "evidence_hashes": hashes,
            }
        )
        output.append(event)
    with ledger_path.open("a", encoding="utf-8") as handle:
        for event in output:
            handle.write(canonical_json(event) + "\n")
    rejected = sum(event["final_decision"] == "REJECTED" for event in output)
    return {"recorded": len(output), "rejected": rejected, "pending_stage_c": len(output) - rejected}


def normalized_tokens(source: str) -> list[str]:
    tokens: list[str] = []
    for match in LEX_RE.finditer(source):
        token = match.group(0)
        if token.startswith("//") or token.startswith("/*"):
            continue
        if token.startswith(("'", '"')):
            tokens.append("STR")
        elif NUMBER_RE.fullmatch(token):
            tokens.append("NUM")
        elif IDENTIFIER_RE.fullmatch(token):
            tokens.append(token.lower())
        else:
            tokens.append(token)
    return tokens


def operation_sequence(tokens: list[str]) -> list[tuple[str, int]]:
    return [
        (token, index)
        for index, token in enumerate(tokens[:-1])
        if IDENTIFIER_RE.fullmatch(token) and token not in CONTROL_CALL_WORDS and tokens[index + 1] == "("
    ]


def operation_pairs(tokens: list[str]) -> dict[tuple[str, str], list[tuple[int, int]]]:
    operations = operation_sequence(tokens)
    pairs: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for (first, first_index), (second, second_index) in zip(operations, operations[1:]):
        pairs.setdefault((first, second), []).append((first_index, second_index))
    return pairs


def shingles(tokens: list[str], width: int = 5) -> set[tuple[str, ...]]:
    return {tuple(tokens[index : index + width]) for index in range(len(tokens) - width + 1)}


def jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def matching_windows(
    query: list[str],
    source: list[str],
    query_pairs: dict[tuple[str, str], list[tuple[int, int]]] | None = None,
    source_pairs: dict[tuple[str, str], list[tuple[int, int]]] | None = None,
) -> list[tuple[int, float, tuple[str, str]]]:
    if len(query) < 20 or len(source) < 20:
        return []
    query_pairs = query_pairs if query_pairs is not None else operation_pairs(query)
    source_pairs = source_pairs if source_pairs is not None else operation_pairs(source)
    shared_pairs = sorted(set(query_pairs) & set(source_pairs))
    if not shared_pairs:
        return []
    query_shingles = shingles(query)
    window_length = min(len(query), len(source))
    pair_by_start: dict[int, tuple[str, str]] = {}
    if len(source) <= len(query):
        for pair in shared_pairs:
            pair_by_start.setdefault(0, pair)
    else:
        for pair in shared_pairs:
            for first_index, second_index in source_pairs[pair]:
                lower = max(0, second_index - window_length + 1)
                upper = min(first_index, len(source) - window_length)
                for start in range(lower, upper + 1):
                    pair_by_start.setdefault(start, pair)
    if not pair_by_start:
        return []
    source_shingles = [tuple(source[index : index + 5]) for index in range(len(source) - 4)]
    shingle_count = window_length - 4
    matching_prefix = [0]
    for source_shingle in source_shingles:
        matching_prefix.append(matching_prefix[-1] + int(source_shingle in query_shingles))
    minimum_matching_occurrences = math.ceil(0.75 * len(query_shingles))
    matches: list[tuple[int, float, tuple[str, str]]] = []
    for start, pair in sorted(pair_by_start.items()):
        matching_occurrences = matching_prefix[start + shingle_count] - matching_prefix[start]
        if matching_occurrences < minimum_matching_occurrences:
            continue
        source_set = set(source_shingles[start : start + shingle_count])
        score = jaccard(query_shingles, source_set)
        if score >= 0.75:
            matches.append((start, score, pair))
    return matches


def extract_query_blocks(repo: Path, base: str, intro: str) -> list[dict[str, Any]]:
    paths_result = run_git(repo, "diff", "--name-only", base, intro)
    paths = [path for path in paths_result["stdout"].splitlines() if is_production_executable(path)]
    diff_result = run_git(repo, "diff", "--no-color", "--unified=12", base, intro, "--", *paths)
    queries: list[dict[str, Any]] = []
    path: str | None = None
    hunk_lines: list[str] = []
    added_lines: list[str] = []
    hunk_start = 0
    current_line = 0

    def add_query(kind: str, lines: list[str], start_line: int) -> None:
        if not path or not lines:
            return
        tokens = normalized_tokens("\n".join(lines))
        if len(tokens) < 20:
            return
        pairs = operation_pairs(tokens)
        if not pairs:
            return
        token_bytes = "\n".join(tokens).encode("utf-8")
        queries.append(
            {
                "kind": kind,
                "path": path,
                "start_line": start_line,
                "tokens": tokens,
                "token_count": len(tokens),
                "normalized_sha256": sha256_bytes(token_bytes),
                "operation_pairs": [list(pair) for pair in sorted(pairs)],
            }
        )

    def flush_added() -> None:
        nonlocal added_lines
        if added_lines:
            add_query("maximal_added_block", added_lines, current_line - len(added_lines))
            added_lines = []

    def flush_hunk() -> None:
        nonlocal hunk_lines
        flush_added()
        if hunk_lines:
            add_query("modified_function_region", hunk_lines, hunk_start)
            hunk_lines = []

    for line in diff_result["stdout"].splitlines():
        if line.startswith("+++ b/"):
            flush_hunk()
            path = line[6:]
            continue
        if line.startswith("@@"):
            flush_hunk()
            match = re.search(r"\+([0-9]+)", line)
            hunk_start = int(match.group(1)) if match else 0
            current_line = hunk_start
            continue
        if not hunk_lines and not added_lines and (line.startswith("diff --git") or line.startswith("--- ")):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])
            hunk_lines.append(line[1:])
            current_line += 1
        elif line.startswith(" "):
            flush_added()
            hunk_lines.append(line[1:])
            current_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            flush_added()
    flush_hunk()
    deduplicated: dict[tuple[str, str, int, str], dict[str, Any]] = {}
    for query in queries:
        key = (query["kind"], query["path"], query["start_line"], query["normalized_sha256"])
        deduplicated[key] = query
    return list(deduplicated.values())


def reachable_executable_blobs(repo: Path, before: str) -> list[tuple[str, str]]:
    # The promisor-clone filter option can itself trigger one remote traversal.
    # Plain --objects walks the locally present commit/tree graph and lists the
    # promised blob IDs and paths without fetching blob contents.
    result = run_git(repo, "rev-list", "--objects", before)
    if result["returncode"] != 0:
        raise ValueError(result["stderr"] or "git rev-list failed")
    blobs: dict[tuple[str, str], None] = {}
    for line in result["stdout"].splitlines():
        fields = line.split(" ", 1)
        if len(fields) != 2:
            continue
        oid, path = fields
        if is_production_executable(path):
            blobs[(oid, path)] = None
    return sorted(blobs)


def iter_blob_bytes(repo: Path, rows: list[tuple[str, str]]) -> Iterable[tuple[str, str, bytes]]:
    process = subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    try:
        for oid, path in rows:
            process.stdin.write(f"{oid}\n".encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("ascii", errors="replace").strip().split()
            if len(header) != 3:
                raise ValueError(f"unexpected cat-file header for {oid}: {' '.join(header)}")
            size = int(header[2])
            raw = process.stdout.read(size)
            separator = process.stdout.read(1)
            if len(raw) != size or separator != b"\n":
                raise ValueError(f"truncated cat-file output for {oid}")
            if header[1] == "blob":
                yield oid, path, raw
        process.stdin.close()
        returncode = process.wait()
        if returncode != 0:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise ValueError(f"git cat-file --batch failed: {stderr}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def source_commits_for_blob(repo: Path, before: str, oid: str, path: str) -> list[tuple[str, int]]:
    history = run_git(repo, "log", "--format=%H %ct", "--reverse", f"--find-object={oid}", before, "--", path)
    matches: list[tuple[str, int]] = []
    for line in history["stdout"].splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        commit, timestamp = fields
        blob = run_git(repo, "rev-parse", f"{commit}:{path}")
        if blob["returncode"] == 0 and blob["stdout"].strip() == oid:
            matches.append((commit, int(timestamp)))
    return matches


def retrieve_source_analogues(repo: Path, base: str, intro: str) -> dict[str, Any]:
    queries = extract_query_blocks(repo, base, intro)
    query_pair_maps = [operation_pairs(query["tokens"]) for query in queries]
    queries_by_pair: dict[tuple[str, str], set[int]] = {}
    for query_index, pair_map in enumerate(query_pair_maps):
        for pair in pair_map:
            queries_by_pair.setdefault(pair, set()).add(query_index)
    blob_rows = reachable_executable_blobs(repo, f"{base}^")
    matches: list[dict[str, Any]] = []
    scanned = 0
    commit_cache: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for oid, path, raw in iter_blob_bytes(repo, blob_rows):
        source = normalized_tokens(raw.decode("utf-8", errors="replace"))
        source_pair_map = operation_pairs(source)
        relevant_queries: set[int] = set()
        for pair in source_pair_map:
            relevant_queries.update(queries_by_pair.get(pair, ()))
        scanned += 1
        for query_index in sorted(relevant_queries):
            query = queries[query_index]
            for start, score, pair in matching_windows(
                query["tokens"], source, query_pair_maps[query_index], source_pair_map
            ):
                cache_key = (oid, path)
                if cache_key not in commit_cache:
                    commit_cache[cache_key] = source_commits_for_blob(repo, f"{base}^", oid, path)
                commits = commit_cache[cache_key]
                for commit, timestamp in commits:
                    window = source[start : start + min(len(query["tokens"]), len(source))]
                    matches.append(
                        {
                            "similarity": score,
                            "source_commit_timestamp": timestamp,
                            "source_commit": commit,
                            "source_blob": oid,
                            "source_path": path,
                            "source_start_token_offset": start,
                            "source_window_token_count": len(window),
                            "source_window_sha256": sha256_bytes("\n".join(window).encode("utf-8")),
                            "shared_operation_pair": list(pair),
                            "query_index": query_index,
                            "query_path": query["path"],
                            "query_offset": query["start_line"],
                            "query_normalized_sha256": query["normalized_sha256"],
                            "query_token_count": query["token_count"],
                        }
                    )
    unique = {
        (
            match["source_commit"], match["source_path"], match["source_start_token_offset"],
            match["query_normalized_sha256"], match["query_offset"],
        ): match
        for match in matches
    }
    ordered = sorted(
        unique.values(),
        key=lambda match: (
            -match["similarity"], match["source_commit_timestamp"], match["source_commit"],
            match["source_path"], match["source_start_token_offset"], match["query_path"], match["query_offset"],
        ),
    )
    public_queries = [{key: value for key, value in query.items() if key != "tokens"} for query in queries]
    return {
        "schema": "v2-prospective-stage-c-source-retrieval-v1",
        "base": base,
        "intro": intro,
        "minimum_tokens": 20,
        "shingle_width": 5,
        "minimum_similarity": 0.75,
        "source_scope": f"{base}^",
        "query_count": len(public_queries),
        "queries": public_queries,
        "source_blob_count": len(blob_rows),
        "source_blobs_scanned": scanned,
        "analogue_count": len(ordered),
        "analogues": ordered,
    }


def run_stage_c(
    ledger_path: Path,
    manifest_path: Path,
    upstream_root: Path,
    evidence_root: Path,
    position: int,
) -> dict[str, Any]:
    validate_registration_ledger(ledger_path, manifest_path)
    events = ledger_events(ledger_path)
    if any(event["event_type"] == "STAGE_C_RETRIEVAL_RESULT" and event["position"] == position for event in events):
        raise ValueError("refusing to append duplicate Stage C event")
    latest = [event for event in events if event["position"] == position][-1]
    if latest["event_type"] != "STAGE_B_RESULT" or latest["final_decision"] != "PENDING_STAGE_C":
        raise ValueError("candidate is not pending Stage C")
    repo = upstream_cache_path(latest["repository"], upstream_root)
    retrieval = retrieve_source_analogues(repo, latest["B"], latest["INTRO/U"])
    retrieval["position"] = position
    evidence_bytes = (json.dumps(retrieval, indent=2, sort_keys=True) + "\n").encode("utf-8")
    evidence_path = evidence_root / f"position-{position:04d}" / "stage-c-source-retrieval.json"
    if evidence_path.exists():
        raise FileExistsError(f"refusing to overwrite {evidence_path}")
    evidence_path.write_bytes(evidence_bytes)
    count = retrieval["analogue_count"]
    event = dict(latest)
    hashes = dict(latest["evidence_hashes"])
    hashes["stage_c_source_retrieval"] = sha256_bytes(evidence_bytes)
    event.update(
        {
            "event_type": "STAGE_C_RETRIEVAL_RESULT",
            "source_analogue_count": count,
            "final_decision": "PENDING_SEMANTIC_REVIEW" if count else "REJECTED",
            "rejection_reason": None if count else "REJECT_NO_QUALIFYING_SOURCE_ANALOGUE",
            "stage_statuses": {
                "A": latest["stage_statuses"]["A"],
                "B": latest["stage_statuses"]["B"],
                "C": "PASS" if count else "FAIL",
            },
            "evidence_hashes": hashes,
        }
    )
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(event) + "\n")
    return {"position": position, "query_count": retrieval["query_count"], "source_blob_count": retrieval["source_blob_count"], "analogue_count": count, "decision": event["final_decision"]}


def validate_semantic_template(template: dict[str, Any]) -> None:
    answers = template.get("answers")
    if not isinstance(answers, dict) or tuple(answers) != SEMANTIC_QUESTIONS:
        raise ValueError("semantic template must contain Q1-Q12 in order")
    for question, answer in answers.items():
        if answer.get("answer") not in {"YES", "NO"}:
            raise ValueError(f"invalid semantic answer for {question}")
        if not answer.get("evidence"):
            raise ValueError(f"missing semantic evidence for {question}")


def record_semantic_review(
    ledger_path: Path,
    manifest_path: Path,
    evidence_root: Path,
    position: int,
) -> dict[str, Any]:
    validate_registration_ledger(ledger_path, manifest_path)
    events = ledger_events(ledger_path)
    if any(event["event_type"] == "SEMANTIC_REVIEW_RESULT" and event["position"] == position for event in events):
        raise ValueError("refusing to append duplicate semantic review event")
    latest = [event for event in events if event["position"] == position][-1]
    if latest["event_type"] != "STAGE_C_RETRIEVAL_RESULT" or latest["final_decision"] != "PENDING_SEMANTIC_REVIEW":
        raise ValueError("candidate is not pending semantic review")
    directory = evidence_root / f"position-{position:04d}"
    retrieval_path = directory / "stage-c-source-retrieval.json"
    rule_path = directory / "semantic-review-rule.json"
    forms_path = directory / "semantic-review-forms.jsonl"
    summary_path = directory / "semantic-review-summary.json"
    if forms_path.exists() or summary_path.exists():
        raise FileExistsError("refusing to overwrite semantic review evidence")
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    rule = json.loads(rule_path.read_text(encoding="utf-8"))
    if rule.get("schema") != "v2-prospective-semantic-review-rule-v1" or rule.get("position") != position:
        raise ValueError("invalid semantic review rule")
    for template in rule["templates"].values():
        validate_semantic_template(template)
    focal_path = rule.get("focal_query_path")
    reviews: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    for occurrence, analogue in enumerate(retrieval["analogues"], start=1):
        category = "focal" if focal_path and analogue["query_path"] == focal_path else "default"
        template = rule["templates"][category]
        context = {
            "occurrence": occurrence,
            "source_commit": analogue["source_commit"],
            "source_path": analogue["source_path"],
            "source_window_sha256": analogue["source_window_sha256"],
            "query_path": analogue["query_path"],
            "query_sha256": analogue["query_normalized_sha256"],
            "similarity": analogue["similarity"],
        }
        answers: dict[str, Any] = {}
        for question, answer in template["answers"].items():
            answers[question] = {
                "answer": answer["answer"],
                "evidence": [item.format(**context) for item in answer["evidence"]],
            }
        all_yes = all(answer["answer"] == "YES" for answer in answers.values())
        review = {
            "schema": "v2-prospective-q1-q12-review-v1",
            "position": position,
            "occurrence": occurrence,
            "retrieval_category": category,
            "analogue": analogue,
            "trust_predicate": template.get("trust_predicate"),
            "answers": answers,
            "decision": "ALL_YES" if all_yes else "REJECTED",
            "failed_questions": [question for question, answer in answers.items() if answer["answer"] == "NO"],
        }
        reviews.append(review)
        if selected is None and all_yes:
            selected = review
            break
    forms_bytes = ("".join(canonical_json(review) + "\n" for review in reviews)).encode("utf-8")
    forms_path.write_bytes(forms_bytes)
    summary = {
        "schema": "v2-prospective-semantic-review-summary-v1",
        "position": position,
        "retrieved_occurrences": retrieval["analogue_count"],
        "reviewed_occurrences": len(reviews),
        "all_yes_occurrence": selected["occurrence"] if selected else None,
        "source_S": selected["analogue"]["source_commit"] if selected else None,
        "decision": "PASS_PENDING_CONTROLS" if selected else "REJECTED",
        "rejection_reason": None if selected else "REJECT_NO_ALL_YES_SOURCE_SAFE_ANALOGUE",
        "forms_sha256": sha256_bytes(forms_bytes),
        "rule_sha256": sha256_bytes(rule_path.read_bytes()),
        "retrieval_sha256": sha256_bytes(retrieval_path.read_bytes()),
    }
    write_json(summary_path, summary)
    event = dict(latest)
    hashes = dict(latest["evidence_hashes"])
    hashes.update(
        {
            "semantic_review_rule": summary["rule_sha256"],
            "semantic_review_forms": summary["forms_sha256"],
            "semantic_review_summary": sha256_bytes(summary_path.read_bytes()),
        }
    )
    event.update(
        {
            "event_type": "SEMANTIC_REVIEW_RESULT",
            "source_S": summary["source_S"],
            "trust_predicate_status": "PASS" if selected else "FAIL",
            "memory_status": "PENDING_CONSTRUCTION" if selected else "NOT_APPLICABLE",
            "final_decision": "PENDING_CONTROLS" if selected else "REJECTED",
            "rejection_reason": summary["rejection_reason"],
            "evidence_hashes": hashes,
        }
    )
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(event) + "\n")
    return summary


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    materialize_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    materialize_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    validate_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    static_parser = subparsers.add_parser("screen-static")
    static_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    static_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    static_parser.add_argument("--upstream-root", type=Path, default=DEFAULT_UPSTREAM_ROOT)
    static_parser.add_argument("--evidence-root", type=Path, default=SCREENING_EVIDENCE_ROOT)
    static_parser.add_argument("--start", type=int, required=True)
    static_parser.add_argument("--end", type=int, required=True)
    stage_b_parser = subparsers.add_parser("record-stage-b")
    stage_b_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    stage_b_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    stage_b_parser.add_argument("--evidence-root", type=Path, default=SCREENING_EVIDENCE_ROOT)
    stage_b_parser.add_argument("--start", type=int, required=True)
    stage_b_parser.add_argument("--end", type=int, required=True)
    stage_c_parser = subparsers.add_parser("run-stage-c")
    stage_c_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    stage_c_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    stage_c_parser.add_argument("--upstream-root", type=Path, default=DEFAULT_UPSTREAM_ROOT)
    stage_c_parser.add_argument("--evidence-root", type=Path, default=SCREENING_EVIDENCE_ROOT)
    stage_c_parser.add_argument("--position", type=int, required=True)
    semantic_parser = subparsers.add_parser("record-semantic-review")
    semantic_parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    semantic_parser.add_argument("--manifest", type=Path, default=SOURCE_MANIFEST_PATH)
    semantic_parser.add_argument("--evidence-root", type=Path, default=SCREENING_EVIDENCE_ROOT)
    semantic_parser.add_argument("--position", type=int, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "materialize":
        print(json.dumps(materialize(args.source_root, args.ledger, args.manifest), sort_keys=True))
        return 0
    if args.command == "validate":
        print(json.dumps(validate_registration_ledger(args.ledger, args.manifest), sort_keys=True))
        return 0
    if args.command == "screen-static":
        print(
            json.dumps(
                screen_static(
                    args.ledger,
                    args.manifest,
                    args.upstream_root,
                    args.evidence_root,
                    args.start,
                    args.end,
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "record-stage-b":
        print(
            json.dumps(
                record_stage_b(
                    args.ledger,
                    args.manifest,
                    args.evidence_root,
                    args.start,
                    args.end,
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "run-stage-c":
        print(
            json.dumps(
                run_stage_c(
                    args.ledger,
                    args.manifest,
                    args.upstream_root,
                    args.evidence_root,
                    args.position,
                ),
                sort_keys=True,
            )
        )
        return 0
    if args.command == "record-semantic-review":
        print(
            json.dumps(
                record_semantic_review(
                    args.ledger,
                    args.manifest,
                    args.evidence_root,
                    args.position,
                ),
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

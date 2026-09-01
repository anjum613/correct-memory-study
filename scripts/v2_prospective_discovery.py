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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/v2-prospective-discovery"
PROTOCOL_PATH = ROOT / "protocols/v2-prospective-family-discovery-v1.json"
DEFAULT_SOURCE_ROOT = ROOT / ".cache/v2-prospective-discovery/sources"
LEDGER_PATH = ARTIFACT_ROOT / "ordered-candidate-ledger.jsonl"
SOURCE_MANIFEST_PATH = ARTIFACT_ROOT / "source-dataset-manifest.json"

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
    )
    return result.stdout


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
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "materialize":
        print(json.dumps(materialize(args.source_root, args.ledger, args.manifest), sort_keys=True))
        return 0
    if args.command == "validate":
        print(json.dumps(validate_registration_ledger(args.ledger, args.manifest), sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

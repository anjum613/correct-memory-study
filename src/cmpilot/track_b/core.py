"""Mechanical filtering and ranking for Track B v0.1."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse


GITHUB_URL = re.compile(r"https?://github\.com/[^\s<>\])}]+", re.IGNORECASE)
COMMIT_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
PACKET_REQUIRED_FIELDS = (
    "seed_id", "advisory_id", "advisory_source_revision", "repository",
    "language", "security_category", "fix_anchor", "relationships",
    "historical_changes", "test_infrastructure", "raw_evidence",
    "unresolved_fields", "history_assessment",
)
FIX_ANCHOR_REQUIRED_FIELDS = (
    "commit", "PR", "issue", "date", "affected_files", "source_files", "test_files",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_independent_input(path: Path, config: Mapping[str, Any]) -> None:
    """Reject Track A and protected paths before reading a retrieval input."""
    resolved = path.resolve()
    for raw_root in config["forbidden_track_a_input_roots"]:
        root = Path(raw_root).resolve()
        if resolved == root or root in resolved.parents:
            raise ValueError(f"Track A path cannot be a Track B input: {resolved}")
    normalized = resolved.as_posix().lower()
    for fragment in config["forbidden_input_path_parts"]:
        if fragment.lower() in normalized:
            raise ValueError(f"protected path cannot be a Track B input: {resolved}")


def _github_urls(advisory: Mapping[str, Any]) -> list[str]:
    urls = [str(reference.get("url", "")) for reference in advisory.get("references", []) if isinstance(reference, Mapping)]
    text = "\n".join(str(advisory.get(field, "")) for field in ("summary", "details"))
    urls.extend(match.group(0).rstrip(".,;:'\"") for match in GITHUB_URL.finditer(text))
    return sorted({url for url in urls if urlparse(url).netloc.lower() == "github.com"})


def extract_github_references(advisory: Mapping[str, Any]) -> dict[str, Any]:
    """Extract concrete GitHub artifacts without dereferencing live pages."""
    repositories: set[str] = set()
    commits: list[dict[str, str]] = []
    pulls: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    other: list[str] = []
    for url in _github_urls(advisory):
        parts = [part for part in urlparse(url).path.split("/") if part]
        if len(parts) < 2 or parts[0].lower() in {"advisories", "security"}:
            continue
        repository = f"{parts[0]}/{parts[1].removesuffix('.git')}"
        repositories.add(repository)
        if len(parts) >= 4 and parts[2] in {"commit", "commits"}:
            sha = parts[3].split("#", 1)[0].split("?", 1)[0]
            if COMMIT_SHA.fullmatch(sha):
                commits.append({"repository": repository, "sha": sha.lower(), "url": url})
            else:
                other.append(url)
        elif len(parts) >= 4 and parts[2] == "pull" and parts[3].isdigit():
            pulls.append({"repository": repository, "number": int(parts[3]), "url": url})
        elif len(parts) >= 4 and parts[2] == "issues" and parts[3].isdigit():
            issues.append({"repository": repository, "number": int(parts[3]), "url": url})
        else:
            other.append(url)

    def unique_artifacts(items: Iterable[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        by_key = {(item["repository"].lower(), item[key]): item for item in items}
        return [by_key[item_key] for item_key in sorted(by_key)]

    unique_commits = unique_artifacts(commits, "sha")
    unique_pulls = unique_artifacts(pulls, "number")
    unique_issues = unique_artifacts(issues, "number")
    preferred_repositories = [item["repository"] for item in unique_commits]
    preferred_repositories += [item["repository"] for item in unique_pulls]
    preferred_repositories += [item["repository"] for item in unique_issues]
    repository = preferred_repositories[0] if preferred_repositories else (sorted(repositories)[0] if repositories else None)
    if repository:
        unique_commits = [item for item in unique_commits if item["repository"].lower() == repository.lower()]
        unique_pulls = [item for item in unique_pulls if item["repository"].lower() == repository.lower()]
        unique_issues = [item for item in unique_issues if item["repository"].lower() == repository.lower()]
    return {
        "repository": repository, "commits": unique_commits, "pulls": unique_pulls,
        "issues": unique_issues, "other_urls": sorted(set(other)), "all_urls": _github_urls(advisory),
    }


def classify_security_category(advisory: Mapping[str, Any], category_rules: Sequence[Mapping[str, Any]]) -> tuple[str | None, dict[str, list[str]]]:
    """Apply the ordered, versioned CWE/keyword map."""
    database_specific = advisory.get("database_specific") or {}
    cwes = {str(value).upper() for value in database_specific.get("cwe_ids", [])}
    text = " ".join(str(advisory.get(field, "")) for field in ("summary", "details")).lower()
    for rule in category_rules:
        matched_cwes = sorted(cwes.intersection(str(value).upper() for value in rule["cwes"]))
        if matched_cwes:
            return str(rule["id"]), {"cwes": matched_cwes, "keywords": []}
    for rule in category_rules:
        matched_keywords = sorted(keyword for keyword in rule["keywords"] if str(keyword).lower() in text)
        if matched_keywords:
            return str(rule["id"]), {"cwes": [], "keywords": matched_keywords}
    return None, {"cwes": [], "keywords": []}


def _language(advisory: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[str | None, list[str]]:
    ecosystems = sorted({str(item.get("package", {}).get("ecosystem", "")) for item in advisory.get("affected", []) if isinstance(item, Mapping)})
    mapped = sorted({str(config["ecosystem_language_mapping"][ecosystem]) for ecosystem in ecosystems if ecosystem in config["ecosystem_language_mapping"]})
    return ("/".join(mapped) if mapped else None), ecosystems


def _score(seed: Mapping[str, Any], config: Mapping[str, Any]) -> tuple[int, dict[str, int]]:
    weights = config["ranking_weights"]
    references = seed["github_references"]
    components = {
        "exact_github_fix_commit": int(bool(references["commits"])),
        "github_pull_request_reference": int(bool(references["pulls"])),
        "github_issue_reference": int(bool(references["issues"])),
        "extra_explicit_github_reference": min(len(references["other_urls"]), int(weights["extra_explicit_github_reference_cap"])),
    }
    total = sum(int(weights[name]) * value for name, value in components.items())
    return total, components


def seed_from_advisory(advisory: Mapping[str, Any], relative_path: str, source_revision: str, config: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if advisory.get("withdrawn"):
        return None, "WITHDRAWN"
    language, ecosystems = _language(advisory, config)
    if language is None:
        return None, "UNSUPPORTED_LANGUAGE"
    category, category_evidence = classify_security_category(advisory, config["security_categories"])
    if category is None:
        return None, "NO_MAPPED_SECURITY_CATEGORY"
    github_references = extract_github_references(advisory)
    if not github_references["repository"]:
        return None, "NO_USABLE_GITHUB_REPOSITORY"
    advisory_id = str(advisory.get("id", ""))
    if not advisory_id:
        return None, "MISSING_ADVISORY_ID"
    packages = sorted({f"{item.get('package', {}).get('ecosystem', '')}:{item.get('package', {}).get('name', '')}" for item in advisory.get("affected", []) if isinstance(item, Mapping)})
    seed: dict[str, Any] = {
        "seed_id": advisory_id, "advisory_id": advisory_id,
        "aliases": sorted(str(value) for value in advisory.get("aliases", [])),
        "summary": str(advisory.get("summary", "")), "published": advisory.get("published"),
        "modified": advisory.get("modified"), "advisory_source_revision": source_revision,
        "advisory_source_path": relative_path, "repository": github_references["repository"],
        "language": language,
        "language_evidence": {"kind": "advisory_package_ecosystem", "ecosystems": ecosystems, "mapping": config["ecosystem_language_mapping"]},
        "security_category": category, "security_category_evidence": category_evidence,
        "packages": packages, "github_references": github_references,
    }
    score, components = _score(seed, config)
    seed["score"] = score
    seed["score_components"] = components
    return seed, None


def rank_and_deduplicate(seeds: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Deduplicate deterministically, then rank by score and advisory ID."""
    ordered_input = sorted(seeds, key=lambda item: str(item["advisory_id"]))
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates = 0
    for seed in ordered_input:
        commits = seed["github_references"]["commits"]
        anchor = commits[0]["sha"] if commits else str(seed["advisory_id"])
        key = (str(seed["repository"]).lower(), anchor.lower())
        if key in unique:
            duplicates += 1
            continue
        unique[key] = seed
    ranked = sorted(unique.values(), key=lambda item: (-int(item["score"]), str(item["advisory_id"])))
    for rank, seed in enumerate(ranked, start=1):
        seed["rank"] = rank
    return ranked, duplicates


def scan_advisories(advisory_root: Path, config: Mapping[str, Any], source_revision: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assert_independent_input(advisory_root, config)
    reasons: Counter[str] = Counter()
    seeds: list[dict[str, Any]] = []
    total = 0
    invalid_json = 0
    for path in sorted(advisory_root.rglob("*.json")):
        total += 1
        try:
            advisory = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid_json += 1
            reasons["INVALID_JSON"] += 1
            continue
        seed, reason = seed_from_advisory(advisory, path.relative_to(advisory_root).as_posix(), source_revision, config)
        if seed is None:
            reasons[str(reason)] += 1
        else:
            seeds.append(seed)
    ranked, duplicate_count = rank_and_deduplicate(seeds)
    if duplicate_count:
        reasons["DUPLICATE_REPOSITORY_FIX_ANCHOR"] += duplicate_count
    counts = {
        "input_advisories": total, "invalid_json": invalid_json,
        "passed_hard_filters_before_deduplication": len(seeds), "duplicates_removed": duplicate_count,
        "ranked_seed_universe": len(ranked), "rejection_reasons": dict(sorted(reasons.items())),
    }
    return ranked, counts


def validate_packet(packet: Mapping[str, Any]) -> None:
    missing = [field for field in PACKET_REQUIRED_FIELDS if field not in packet]
    if missing:
        raise ValueError(f"packet missing required fields: {', '.join(missing)}")
    if not isinstance(packet["fix_anchor"], Mapping):
        raise ValueError("packet fix_anchor must be an object")
    missing_anchor = [field for field in FIX_ANCHOR_REQUIRED_FIELDS if field not in packet["fix_anchor"]]
    if missing_anchor:
        raise ValueError(f"packet fix_anchor missing required fields: {', '.join(missing_anchor)}")
    if packet["history_assessment"] not in {"ENOUGH_HISTORY", "THIN_HISTORY", "NO_USEFUL_HISTORY"}:
        raise ValueError("packet history_assessment is invalid")

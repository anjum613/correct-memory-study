"""Bounded GitHub and local-history expansion for Track B v0.1."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Mapping, Sequence

from .core import sha256_bytes, validate_packet


NUMBER_REFERENCE = re.compile(r"(?<![\w/])#(?P<number>[1-9][0-9]*)")
GITHUB_ARTIFACT_URL = re.compile(
    r"https?://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/(?P<kind>issues|pull)/(?P<number>[1-9][0-9]*)",
    re.IGNORECASE,
)
PR_IN_COMMIT = re.compile(r"(?:\(#(?P<paren>[0-9]+)\)|\bPR\s*#(?P<pr>[0-9]+))", re.IGNORECASE)
TEST_PARTS = {"test", "tests", "testing", "spec", "specs", "__tests__"}
TEST_CONFIG_NAMES = {
    "pytest.ini", "tox.ini", "jest.config.js", "jest.config.ts", "vitest.config.js",
    "vitest.config.ts", "package.json", "pyproject.toml", "setup.cfg",
}


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "__", value).strip("_")
    return clean[:180] or hashlib.sha256(value.encode()).hexdigest()


def _run(arguments: Sequence[str], cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(arguments), cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=timeout,
    )


class GitHubClient:
    def __init__(self, raw_root: Path, api_version: str) -> None:
        self.raw_root = raw_root
        self.api_version = api_version
        self.evidence: list[dict[str, Any]] = []
        self.errors: list[str] = []

    def get(self, endpoint: str) -> Any | None:
        path = self.raw_root / "github-api" / f"{_safe_name(endpoint)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raw = path.read_bytes()
        else:
            completed = _run([
                "gh", "api", "-H", "Accept: application/vnd.github+json", "-H",
                f"X-GitHub-Api-Version: {self.api_version}", endpoint,
            ])
            if completed.returncode != 0:
                message = completed.stderr.decode("utf-8", "replace").strip().splitlines()
                self.errors.append(f"{endpoint}: {message[-1] if message else 'GitHub API failed'}")
                return None
            raw = completed.stdout
            path.write_bytes(raw)
        evidence = {
            "kind": "github_api", "api_identifier": endpoint,
            "path": path.as_posix(), "sha256": sha256_bytes(raw),
        }
        if evidence not in self.evidence:
            self.evidence.append(evidence)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self.errors.append(f"{endpoint}: invalid JSON response")
            return None


def _is_test(path: str) -> bool:
    pure = PurePosixPath(path.lower())
    return bool(TEST_PARTS.intersection(pure.parts)) or pure.name.startswith("test_") or pure.stem.endswith((".test", ".spec", "_test"))


def _source_language(path: str, config: Mapping[str, Any]) -> str | None:
    suffix = PurePosixPath(path).suffix.lower()
    for language, suffixes in config["supported_languages"].items():
        if suffix in suffixes:
            return str(language)
    return None


def commit_file_facts(commit_data: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic supported-source and test facts from a commit response."""
    file_records = [item for item in commit_data.get("files", []) if item.get("filename")]
    affected_files = sorted(str(item["filename"]) for item in file_records)
    source_files = sorted(
        path for path in affected_files if _source_language(path, config) and not _is_test(path)
    )
    test_files = sorted(path for path in affected_files if _is_test(path))
    languages = sorted(
        {language for path in source_files if (language := _source_language(path, config))}
    )
    return {
        "affected_files": affected_files,
        "source_files": source_files,
        "test_files": test_files,
        "languages": languages,
        "changed_file_count": len(affected_files),
        "additions": sum(int(item.get("additions", 0)) for item in file_records),
        "deletions": sum(int(item.get("deletions", 0)) for item in file_records),
    }


def _artifact_refs(text: str, repository: str) -> list[dict[str, Any]]:
    found: dict[tuple[str, int], dict[str, Any]] = {}
    for match in NUMBER_REFERENCE.finditer(text):
        number = int(match.group("number"))
        found[(repository.lower(), number)] = {
            "repository": repository, "number": number,
            "relation_type": "same_repository_number_reference", "matched_text": match.group(0),
        }
    for match in GITHUB_ARTIFACT_URL.finditer(text):
        target_repository = f"{match.group('owner')}/{match.group('repo')}"
        number = int(match.group("number"))
        found[(target_repository.lower(), number)] = {
            "repository": target_repository, "number": number,
            "relation_type": "explicit_github_url", "matched_text": match.group(0),
        }
    return [found[key] for key in sorted(found)]


def _relation(source: str, target: str, relation_type: str, timestamp: str | None, provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_artifact": source, "target_artifact": target,
        "relation_type": relation_type, "timestamp": timestamp,
        "concrete_provenance": dict(provenance),
    }


def _git(repository: Path, arguments: Sequence[str], timeout: int = 180) -> bytes | None:
    completed = _run(["git", *arguments], cwd=repository, timeout=timeout)
    return completed.stdout if completed.returncode == 0 else None


def _ensure_repository(repository: str, cache_root: Path, fix_commit: str | None, depth: int) -> tuple[Path | None, list[str]]:
    errors: list[str] = []
    local = cache_root / "repositories" / repository.replace("/", "__")
    if not (local / ".git").exists():
        local.parent.mkdir(parents=True, exist_ok=True)
        completed = _run([
            "git", "clone", "--filter=blob:none", "--no-checkout", f"--depth={depth}",
            f"https://github.com/{repository}.git", str(local),
        ], timeout=300)
        if completed.returncode != 0:
            errors.append(f"repository clone failed: {completed.stderr.decode('utf-8', 'replace').strip()[-400:]}")
            return None, errors
    if fix_commit and _git(local, ["cat-file", "-e", f"{fix_commit}^{{commit}}"] ) is None:
        completed = _run(["git", "fetch", f"--depth={depth}", "origin", fix_commit], cwd=local, timeout=300)
        if completed.returncode != 0:
            errors.append(f"fix commit fetch failed: {completed.stderr.decode('utf-8', 'replace').strip()[-400:]}")
    return local, errors


def _write_raw(path: Path, raw: bytes, kind: str, identifier: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"kind": kind, "identifier": identifier, "path": path.as_posix(), "sha256": sha256_bytes(raw)}


def _parse_log(raw: bytes) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for record in raw.decode("utf-8", "replace").split("\x1e"):
        fields = record.strip().split("\x1f", 2)
        if len(fields) == 3:
            records.append({"commit": fields[0], "date": fields[1], "subject": fields[2]})
    return records


def _history(local: Path, repository: str, fix_commit: str, source_files: Sequence[str], raw_root: Path, config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    changes: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    max_commits = int(config["max_prior_commits_per_relevant_file"])
    for path in source_files[: int(config["max_relevant_files"])]:
        raw = _git(local, [
            "log", "--follow", f"--max-count={max_commits}",
            "--format=%H%x1f%cI%x1f%s%x1e", f"{fix_commit}^", "--", path,
        ])
        if raw is None:
            continue
        evidence.append(_write_raw(
            raw_root / "git-history" / f"{_safe_name(repository)}__{_safe_name(path)}__log.txt",
            raw, "git_log_follow", f"git log --follow {fix_commit}^ -- {path}",
        ))
        for item in _parse_log(raw):
            commit = item["commit"]
            record = changes.setdefault(commit, {
                "commit": commit, "associated_PR": None, "issue": None,
                "date": item["date"], "affected_files": [], "relation_evidence": [],
                "subject": item["subject"],
            })
            if path not in record["affected_files"]:
                record["affected_files"].append(path)
            record["relation_evidence"].append({"type": "prior_file_history", "path": path, "command": "git log --follow"})
            pr_match = PR_IN_COMMIT.search(item["subject"])
            if pr_match:
                number = int(pr_match.group("paren") or pr_match.group("pr"))
                record["associated_PR"] = number
                relationships.append(_relation(
                    f"{repository}@{commit}", f"{repository}#{number}",
                    "commit_message_pull_reference", item["date"],
                    {"source": "git log --follow", "path": path, "subject": item["subject"]},
                ))
        blame = _git(local, [
            "blame", "--line-porcelain", "-L", f"1,{int(config['max_blame_lines'])}",
            f"{fix_commit}^", "--", path,
        ])
        if blame is not None:
            evidence.append(_write_raw(
                raw_root / "git-history" / f"{_safe_name(repository)}__{_safe_name(path)}__blame.txt",
                blame, "git_blame", f"git blame -L 1,{config['max_blame_lines']} {fix_commit}^ -- {path}",
            ))
    ordered = sorted(changes.values(), key=lambda item: (item["date"], item["commit"]), reverse=True)
    return ordered, relationships, evidence


def expand_seed(seed: Mapping[str, Any], run_root: Path, cache_root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    repository = str(seed["repository"])
    owner, name = repository.split("/", 1)
    raw_root = run_root / "raw" / str(seed["seed_id"])
    client = GitHubClient(raw_root, str(config["github_api_version"]))
    refs = seed["github_references"]
    fix_commit = refs["commits"][0]["sha"] if refs["commits"] else None
    relationships: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for item in refs["commits"]:
        relationships.append(_relation(
            str(seed["advisory_id"]), f"{repository}@{item['sha']}",
            "advisory_explicit_commit_reference", seed.get("published"),
            {"advisory_source_path": seed["advisory_source_path"], "url": item["url"]},
        ))
    for kind, relation_type in (("pulls", "advisory_explicit_pull_reference"), ("issues", "advisory_explicit_issue_reference")):
        for item in refs[kind]:
            relationships.append(_relation(
                str(seed["advisory_id"]), f"{repository}#{item['number']}", relation_type,
                seed.get("published"), {"advisory_source_path": seed["advisory_source_path"], "url": item["url"]},
            ))

    commit_data: Mapping[str, Any] = {}
    affected_files: list[str] = []
    if fix_commit:
        response = client.get(f"repos/{owner}/{name}/commits/{fix_commit}")
        if isinstance(response, Mapping):
            commit_data = response
            affected_files = commit_file_facts(response, config)["affected_files"]
        else:
            unresolved.append("fix_anchor.commit_metadata")
    else:
        unresolved.append("fix_anchor.commit")

    pr_numbers = {int(item["number"]) for item in refs["pulls"]}
    if fix_commit:
        associated_endpoint = f"repos/{owner}/{name}/commits/{fix_commit}/pulls?per_page=100"
        associated = client.get(associated_endpoint)
        if isinstance(associated, list):
            for pull in associated:
                number = int(pull["number"])
                pr_numbers.add(number)
                relationships.append(_relation(
                    f"{repository}@{fix_commit}", f"{repository}#{number}",
                    "github_associated_pull_request", pull.get("created_at"),
                    {"api_identifier": associated_endpoint},
                ))

    initial_issue_numbers = {int(item["number"]) for item in refs["issues"]}
    artifact_queue: deque[tuple[str, int, int]] = deque((repository, number, 0) for number in sorted(pr_numbers | initial_issue_numbers))
    seen_artifacts: set[tuple[str, int]] = set()
    primary_pr: int | None = min(pr_numbers) if pr_numbers else None
    primary_issue: int | None = min(initial_issue_numbers) if initial_issue_numbers else None
    while artifact_queue and len(seen_artifacts) < int(config["max_relation_artifacts"]):
        artifact_repository, number, hop = artifact_queue.popleft()
        key = (artifact_repository.lower(), number)
        if key in seen_artifacts or hop > int(config["max_relation_hops"]):
            continue
        seen_artifacts.add(key)
        artifact_owner, artifact_name = artifact_repository.split("/", 1)
        issue_endpoint = f"repos/{artifact_owner}/{artifact_name}/issues/{number}"
        issue_data = client.get(issue_endpoint)
        if not isinstance(issue_data, Mapping):
            unresolved.append(f"artifact:{artifact_repository}#{number}")
            continue
        is_pull = "pull_request" in issue_data
        if is_pull and artifact_repository.lower() == repository.lower():
            pr_numbers.add(number)
            primary_pr = primary_pr or number
        elif artifact_repository.lower() == repository.lower():
            primary_issue = primary_issue or number
        artifact = f"{artifact_repository}#{number}"
        text = f"{issue_data.get('title', '')}\n{issue_data.get('body') or ''}"
        for target in _artifact_refs(text, artifact_repository):
            target_artifact = f"{target['repository']}#{target['number']}"
            if target_artifact == artifact:
                continue
            relationships.append(_relation(
                artifact, target_artifact, target["relation_type"], issue_data.get("created_at"),
                {"api_identifier": issue_endpoint, "matched_text": target["matched_text"]},
            ))
            if hop < int(config["max_relation_hops"]):
                artifact_queue.append((target["repository"], int(target["number"]), hop + 1))
        timeline_endpoint = f"repos/{artifact_owner}/{artifact_name}/issues/{number}/timeline?per_page=100"
        timeline = client.get(timeline_endpoint)
        if isinstance(timeline, list):
            for event in timeline:
                source_url = ((event.get("source") or {}).get("issue") or {}).get("html_url")
                if source_url:
                    for target in _artifact_refs(str(source_url), artifact_repository):
                        relationships.append(_relation(
                            artifact, f"{target['repository']}#{target['number']}",
                            f"github_timeline_{event.get('event', 'event')}", event.get("created_at"),
                            {"api_identifier": timeline_endpoint, "event_id": event.get("id")},
                        ))
        if is_pull:
            client.get(f"repos/{artifact_owner}/{artifact_name}/pulls/{number}")

    source_files = sorted(path for path in affected_files if _source_language(path, config) and not _is_test(path))
    test_files = sorted(path for path in affected_files if _is_test(path))
    local, local_errors = _ensure_repository(repository, cache_root, fix_commit, int(config["repository_history_fetch_depth"]))
    unresolved.extend(local_errors)
    raw_evidence = list(client.evidence)
    historical_changes: list[dict[str, Any]] = []
    tree: bytes | None = None
    if local and fix_commit:
        if not affected_files:
            raw_names = _git(local, ["diff-tree", "--no-commit-id", "--name-only", "-r", fix_commit])
            if raw_names is not None:
                affected_files = sorted(filter(None, raw_names.decode("utf-8", "replace").splitlines()))
                source_files = sorted(path for path in affected_files if _source_language(path, config) and not _is_test(path))
                test_files = sorted(path for path in affected_files if _is_test(path))
        show = _git(local, ["show", "--format=fuller", "--stat", "--patch", fix_commit])
        if show is not None:
            raw_evidence.append(_write_raw(
                raw_root / "git-history" / f"{fix_commit}__show.patch", show,
                "git_show", f"git show {fix_commit}",
            ))
        history, history_relationships, history_evidence = _history(
            local, repository, fix_commit, source_files, raw_root, config,
        )
        historical_changes = history
        relationships.extend(history_relationships)
        raw_evidence.extend(history_evidence)
        tree = _git(local, ["ls-tree", "-r", "--name-only", fix_commit])
    tree_paths = tree.decode("utf-8", "replace").splitlines() if tree else []
    infrastructure_examples = sorted(path for path in tree_paths if _is_test(path) or PurePosixPath(path).name.lower() in TEST_CONFIG_NAMES)[:50]
    languages = sorted({language for path in source_files if (language := _source_language(path, config))})
    language = "/".join(languages) if languages else str(seed["language"])
    relation_keys: set[str] = set()
    unique_relationships: list[dict[str, Any]] = []
    for item in sorted(relationships, key=lambda value: (
        str(value["source_artifact"]), str(value["target_artifact"]),
        str(value["relation_type"]), str(value.get("timestamp") or ""),
    )):
        key = json.dumps(item, sort_keys=True)
        if key not in relation_keys:
            relation_keys.add(key)
            unique_relationships.append(item)
    if source_files and len(historical_changes) >= 5 and unique_relationships:
        assessment = "ENOUGH_HISTORY"
    elif source_files or historical_changes or unique_relationships:
        assessment = "THIN_HISTORY"
    else:
        assessment = "NO_USEFUL_HISTORY"
    fix_date = (((commit_data.get("commit") or {}).get("committer") or {}).get("date") if commit_data else None)
    if primary_issue is None:
        unresolved.append("fix_anchor.issue")
    if primary_pr is None:
        unresolved.append("fix_anchor.PR")
    if not source_files:
        unresolved.append("fix_anchor.source_files")
    if not historical_changes:
        unresolved.append("historical_changes")
    unresolved.extend(client.errors)
    packet = {
        "packet_schema": "historical-trust-transition-packet-v0.1",
        "seed_id": seed["seed_id"], "advisory_id": seed["advisory_id"],
        "advisory_aliases": seed["aliases"], "advisory_source_revision": seed["advisory_source_revision"],
        "advisory_source_path": seed["advisory_source_path"], "repository": repository,
        "language": language, "language_evidence": seed["language_evidence"],
        "security_category": seed["security_category"], "security_category_evidence": seed["security_category_evidence"],
        "fix_anchor": {
            "commit": fix_commit, "PR": primary_pr, "issue": primary_issue, "date": fix_date,
            "affected_files": affected_files, "source_files": source_files, "test_files": test_files,
        },
        "relationships": unique_relationships, "historical_changes": historical_changes,
        "test_infrastructure": {
            "present": bool(infrastructure_examples), "changed_test_files": test_files,
            "repository_examples": infrastructure_examples,
        },
        "raw_evidence": sorted(raw_evidence, key=lambda item: (item["kind"], item["path"])),
        "unresolved_fields": sorted(set(unresolved)), "history_assessment": assessment,
        "semantic_status": "NOT_REVIEWED_AS_S_C_OR_I",
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    validate_packet(packet)
    return packet

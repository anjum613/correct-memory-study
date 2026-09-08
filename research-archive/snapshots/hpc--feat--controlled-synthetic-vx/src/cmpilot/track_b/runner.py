"""Run artifact generation for historical-trust-transition-retrieval-v0.1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from typing import Any, Mapping, Sequence

from .core import assert_independent_input, scan_advisories, sha256_file
from .github import GitHubClient, commit_file_facts, expand_seed


def _git(arguments: Sequence[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    return completed.stdout.strip()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(repository_root: Path, advisory_repository: Path, run_root: Path, config_path: Path, expand_count: int | None = None) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert_independent_input(advisory_repository, config)
    assert_independent_input(run_root, config)
    source_revision = _git(["rev-parse", "HEAD"], advisory_repository)
    source_tree = _git(["rev-parse", "HEAD:advisories/github-reviewed"], advisory_repository)
    implementation_revision = _git(["rev-parse", "HEAD"], repository_root)
    advisory_root = advisory_repository / "advisories" / "github-reviewed"
    started_at = _now()
    run_root.mkdir(parents=True, exist_ok=False)
    ranked, filter_counts = scan_advisories(advisory_root, config, source_revision)
    ranking_client = GitHubClient(run_root / "raw" / "ranking", str(config["github_api_version"]))
    selected: list[dict[str, Any]] = []
    post_ranking_rejections: dict[str, int] = {}
    for preliminary_seed in ranked[: int(config["max_fix_fact_candidates"])]:
        seed = dict(preliminary_seed)
        commits = seed["github_references"]["commits"]
        if not commits:
            reason = "NO_EXACT_FIX_COMMIT"
            post_ranking_rejections[reason] = post_ranking_rejections.get(reason, 0) + 1
            continue
        commit = commits[0]
        owner, name = str(seed["repository"]).split("/", 1)
        endpoint = f"repos/{owner}/{name}/commits/{commit['sha']}"
        commit_data = ranking_client.get(endpoint)
        if not isinstance(commit_data, Mapping):
            reason = "FIX_COMMIT_UNAVAILABLE"
            post_ranking_rejections[reason] = post_ranking_rejections.get(reason, 0) + 1
            continue
        facts = commit_file_facts(commit_data, config)
        if not facts["source_files"]:
            reason = "NO_SUPPORTED_SOURCE_FILE_IN_FIX"
            post_ranking_rejections[reason] = post_ranking_rejections.get(reason, 0) + 1
            continue
        seed["preliminary_rank"] = seed["rank"]
        seed["rank"] = len(selected) + 1
        seed["language"] = "/".join(facts["languages"])
        seed["language_evidence"] = {
            "kind": "fix_commit_changed_source_files",
            "api_identifier": endpoint,
            "source_files": facts["source_files"],
        }
        seed["fix_file_facts"] = facts
        selected.append(seed)
        if len(selected) == int(config["max_seeds"]):
            break
    filter_counts["post_ranking_fix_fact_rejections"] = dict(sorted(post_ranking_rejections.items()))
    filter_counts["fix_fact_candidates_examined"] = sum(post_ranking_rejections.values()) + len(selected)
    if len(selected) < int(config["max_seeds"]):
        raise RuntimeError(f"only {len(selected)} seeds survived fix-file validation")
    frozen_config = dict(config)
    frozen_config["source_config_path"] = config_path.relative_to(repository_root).as_posix()
    _write_json(run_root / "config.json", frozen_config)
    provenance = {
        "tool_id": config["tool_id"], "implementation_repository": repository_root.as_posix(),
        "implementation_git_commit": implementation_revision,
        "advisory_source_repository": config["advisory_repository_url"],
        "advisory_source_commit": source_revision, "advisory_reviewed_tree": source_tree,
        "advisory_local_checkout": advisory_repository.as_posix(), "retrieval_timestamp": started_at,
        "configuration_path": config_path.relative_to(repository_root).as_posix(),
        "configuration_sha256": sha256_file(config_path),
        "supported_language_source": config["supported_language_source"],
        "versions": {
            "python": platform.python_version(),
            "gh": subprocess.run(["gh", "--version"], text=True, stdout=subprocess.PIPE, check=True).stdout.splitlines()[0],
            "git": subprocess.run(["git", "--version"], text=True, stdout=subprocess.PIPE, check=True).stdout.strip(),
            "cmpilot": importlib.metadata.version("cmpilot"),
        },
    }
    _write_json(run_root / "source-provenance.json", provenance)
    _write_jsonl(run_root / "seeds.jsonl", selected)
    ranking_records = [{
        "rank": seed["rank"], "seed_id": seed["seed_id"], "advisory_id": seed["advisory_id"],
        "repository": seed["repository"], "language": seed["language"],
        "security_category": seed["security_category"], "score": seed["score"],
        "score_components": seed["score_components"], "tie_breaker": seed["advisory_id"],
    } for seed in selected]
    _write_jsonl(run_root / "seed-ranking.jsonl", ranking_records)
    packet_summaries: list[dict[str, Any]] = []
    actual_expand_count = min(len(selected), int(expand_count if expand_count is not None else config["expand_top_seeds"]))
    cache_root = repository_root / ".track-b-cache"
    for seed in selected[:actual_expand_count]:
        packet = expand_seed(seed, run_root, cache_root, config)
        packet_path = run_root / "packets" / f"{seed['seed_id']}.json"
        _write_json(packet_path, packet)
        packet_summaries.append({
            "rank": seed["rank"], "seed_id": seed["seed_id"],
            "packet_path": packet_path.relative_to(run_root).as_posix(),
            "packet_sha256": sha256_file(packet_path), "relationships": len(packet["relationships"]),
            "historical_changes": len(packet["historical_changes"]),
            "history_assessment": packet["history_assessment"], "unresolved_fields": packet["unresolved_fields"],
        })
    rate_client = GitHubClient(run_root / "raw" / "run", str(config["github_api_version"]))
    rate = rate_client.get("rate_limit")
    github_core_rate = (rate or {}).get("resources", {}).get("core") if isinstance(rate, Mapping) else None
    output_files = [run_root / name for name in ("config.json", "source-provenance.json", "seeds.jsonl", "seed-ranking.jsonl")]
    summary = {
        "tool_id": config["tool_id"], "started_at": started_at, "completed_at": _now(),
        "filter_counts": filter_counts, "max_seeds": config["max_seeds"],
        "selected_seed_count": len(selected), "expanded_packet_count": len(packet_summaries),
        "packets": packet_summaries, "github_core_rate_limit_at_completion": github_core_rate,
        "output_sha256": {path.relative_to(run_root).as_posix(): sha256_file(path) for path in output_files},
        "semantic_decisions_performed": False,
    }
    _write_json(run_root / "run-summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="historical-trust-transition-retrieval-v0.1")
    parser.add_argument("--advisory-repository", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("track_b/config-v0.1.json"))
    parser.add_argument("--expand-count", type=int)
    arguments = parser.parse_args(argv)
    repository_root = Path.cwd().resolve()
    summary = run(
        repository_root, arguments.advisory_repository.resolve(), arguments.run_root.resolve(),
        arguments.config.resolve(), arguments.expand_count,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

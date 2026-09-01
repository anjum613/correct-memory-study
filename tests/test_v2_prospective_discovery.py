import json
import subprocess
from pathlib import Path

import pytest

from scripts.v2_prospective_discovery import (
    Candidate,
    commit_from_url,
    materialize,
    materialize_primary,
    normalize_cve,
    normalize_repository,
    sha256_bytes,
    validate_registration_ledger,
)


def test_normalization_and_commit_parsing() -> None:
    assert normalize_repository(" HTTPS://GitHub.com/Org/Repo.git/ ") == "https://github.com/org/repo"
    assert normalize_repository("git@github.com:Org/Repo.git") == "https://github.com/org/repo"
    assert normalize_cve("prefix cve-2020-12345 suffix") == "CVE-2020-12345"
    assert normalize_cve("GHSA-abcd") is None
    assert commit_from_url("https://github.com/o/r/commit/ABCDEF0123456789") == "abcdef0123456789"


def test_primary_intersection_expands_fixes_and_excludes_matched_vul4j() -> None:
    vcc = json.dumps(
        [
            {
                "cve": "CVE-2020-1234",
                "repository": "https://github.com/Org/Repo.git",
                "introducing": "a" * 40,
                "fixing": ["b" * 40, "c" * 40],
            },
            {
                "cve": "CVE-2021-9999",
                "repository": "https://github.com/Else/Repo",
                "introducing": "d" * 40,
                "fixing": ["e" * 40],
            },
        ]
    ).encode()
    vul4j = (
        "no,vul_id,cve_id,repo_slug,human_patch,build_system,compile_cmd,test_cmd,failing_tests,cwe_id\n"
        "1,VUL4J-1,CVE-2020-1234,org/repo,https://github.com/org/repo/commit/"
        + "b" * 40
        + ",Maven,compile,test,Foo#bar,CWE-1\n"
        "2,VUL4J-2,CVE-2022-7777,new/repo,https://github.com/new/repo/commit/"
        + "f" * 40
        + ",Maven,compile,test,Bar#baz,CWE-2\n"
    ).encode()
    candidates, matched = materialize_primary(vcc, vul4j)
    assert matched == {1}
    assert [candidate.source_tier for candidate in candidates] == [
        "TIER_1_VCC_EVAL_INTERSECTION_VUL4J",
        "TIER_1_VCC_EVAL_INTERSECTION_VUL4J",
        "TIER_2_REMAINING_VCC_EVAL_WITH_UPSTREAM_WITNESS_GATE",
        "TIER_3_REMAINING_VUL4J_WITH_INDEPENDENT_EXACT_INTRO_GATE",
    ]
    assert candidates[0].metadata["vul4j_ids"] == ["VUL4J-1"]
    assert candidates[-1].intro is None


def test_candidate_sort_key_places_valid_cve_before_native_identifier() -> None:
    kwargs = dict(
        source_tier="TIER_4A_VULNLOC",
        repository="https://github.com/o/r",
        intro=None,
        fix=None,
        dataset_ordinal=1,
        metadata={},
    )
    cve = Candidate(dataset_entry="z", cve="CVE-2020-1234", **kwargs)
    native = Candidate(dataset_entry="a", cve=None, **kwargs)
    assert cve.sort_key < native.sort_key


def _make_repo(path: Path, files: dict[str, str]) -> tuple[str, str]:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    for name, value in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD^{tree}"], check=True, capture_output=True, text=True).stdout.strip()
    return commit, tree


def test_materialize_refuses_to_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "ledger.jsonl"
    manifest = tmp_path / "manifest.json"
    ledger.write_text("already frozen\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        materialize(tmp_path / "sources", ledger, manifest)


def test_registration_validator_allows_only_append_after_hashed_prefix(tmp_path: Path) -> None:
    row = {
        "event_type": "CANDIDATE_REGISTERED",
        "position": 1,
        "source_tier": "TIER_1_VCC_EVAL_INTERSECTION_VUL4J",
        "final_decision": "NOT_SCREENED",
    }
    prefix = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(prefix + b'{"event_type":"SCREENING_DECISION"}\n')
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "initial_registration_ledger_bytes": len(prefix),
                "initial_registration_ledger_sha256": sha256_bytes(prefix),
                "candidate_universe_size": 1,
                "candidate_counts_by_tier": {"TIER_1_VCC_EVAL_INTERSECTION_VUL4J": 1},
            }
        )
    )
    result = validate_registration_ledger(ledger, manifest)
    assert result["candidate_universe_size"] == 1
    assert result["append_bytes"] > 0

    ledger.write_bytes(b"x" + ledger.read_bytes()[1:])
    with pytest.raises(ValueError, match="prefix hash mismatch"):
        validate_registration_ledger(ledger, manifest)

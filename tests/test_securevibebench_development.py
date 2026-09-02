import json
import subprocess
from pathlib import Path

import pytest

from scripts.securevibebench_development import extract_crash_state

from cmpilot.securevibebench_development import (
    SEEN_IDS,
    SourceCandidate,
    classify_functional_result,
    classify_security_result,
    collapse_duplicates,
    deduplication_key,
    deterministic_order,
    guard_instance_access,
    load_seen_ids,
    memory_leakage_findings,
    normalize_task_metadata,
    procedure_representation,
    procedure_similarity,
    render_source_memory,
    source_lock_valid,
    uniquely_selected,
    validate_evidence_packet,
    verify_bur_ancestry,
)


ROOT = Path(__file__).resolve().parents[1]


def test_seen_set_is_exact_and_excludes_unseen() -> None:
    path = ROOT / "protocols/securevibebench-seen-development-set.txt"
    assert load_seen_ids(path) == SEEN_IDS
    all_ids = {*SEEN_IDS, "99999"}
    assert all_ids - set(load_seen_ids(path)) == {"99999"}


def test_unseen_implementation_access_guard() -> None:
    guard_instance_access("99999", SEEN_IDS, fields=["localid", "repo_url"])
    with pytest.raises(PermissionError, match="implementation access denied"):
        guard_instance_access("99999", SEEN_IDS, implementation_access=True)
    with pytest.raises(PermissionError, match="non-enumeration fields"):
        guard_instance_access("99999", SEEN_IDS, fields=["description"])
    guard_instance_access("26952", SEEN_IDS, fields=["description"], implementation_access=True)


def test_metadata_normalization_and_source_lock() -> None:
    row = {"localid": 1, "repo_url": "HTTPS://GitHub.com/O/R.git/", "vic": "ABCD", "repo_cwd": " /src/r ", "description": "x\r\n"}
    assert normalize_task_metadata(row) == {
        "description": "x",
        "localid": "1",
        "repo_cwd": "/src/r",
        "repo_url": "https://github.com/o/r",
        "vic": "abcd",
    }
    lock = {
        "securevibebench_commit": "a" * 40,
        "securevibebench_dataset_revision": "b" * 40,
        "arvo_commit": "c" * 40,
        "arvo_meta_commit": "d" * 40,
        "normalized_task_metadata_sha256": "e" * 64,
        "dataset_parquet_sha256": "f" * 64,
    }
    assert source_lock_valid(lock)
    lock["arvo_commit"] = "main"
    assert not source_lock_valid(lock)


def test_pinned_source_lock_and_unseen_artifacts() -> None:
    artifact_root = ROOT / "artifacts/v2-securevibebench-development"
    lock = json.loads((artifact_root / "source-lock.json").read_text())
    assert source_lock_valid(lock)
    assert lock["securevibebench_commit"] == "47c452becd3011ad948876e7cf0f3cca5846802d"
    assert lock["securevibebench_dataset_revision"] == "d6a5edd34e594afdd19ec610e65deddd9dbc625f"
    universe = json.loads((artifact_root / "unseen-universe.json").read_text())
    assert universe["raw_task_count"] == 105
    assert universe["unseen_task_count"] == 97
    assert set(universe["unseen_ids"]).isdisjoint(SEEN_IDS)
    assert universe["implementation_details_inspected"] is False


def _repo_with_bur(path: Path) -> tuple[str, str, str]:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    target = path / "x.c"
    commits = []
    for value in ("base\n", "unsafe\n", "secure\n"):
        target.write_text(value)
        subprocess.run(["git", "-C", str(path), "add", "x.c"], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-qm", value.strip()], check=True)
        commits.append(subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip())
    return tuple(commits)  # type: ignore[return-value]


def test_bur_ancestry(tmp_path: Path) -> None:
    b, u, r = _repo_with_bur(tmp_path / "repo")
    result = verify_bur_ancestry(tmp_path / "repo", u, r)
    assert (result["B"], result["U"], result["R"]) == (b, u, r)
    assert result["u_parent_count"] == 1


def test_duplicate_collapse_and_deterministic_order() -> None:
    base = {"repo_url": "https://github.com/o/r.git", "vic": "a", "vfc": "b", "fingerprint": "c"}
    rows = [
        {**base, "localid": "11060"},
        {**base, "localid": "11074", "fingerprint": "d"},
        {**base, "localid": "99999", "vic": "different"},
    ]
    assert deduplication_key(rows[0]) == deduplication_key(rows[1])
    collapsed = collapse_duplicates(rows)
    assert sorted(group["member_ids"] for group in collapsed) == [["11060", "11074"], ["99999"]]
    duplicate = next(group for group in collapsed if len(group["member_ids"]) == 2)
    assert duplicate["single_focal_fingerprint"] is False
    salt = "correct-memory-securevibebench-v1"
    assert deterministic_order(["3", "2", "1"], salt) == deterministic_order(["1", "2", "3"], salt)


def test_functional_and_security_classification() -> None:
    assert classify_functional_result(build_exit=1, oracle_exit=None, parsed_pass=None) == "INFRA_BUILD_FAILURE"
    assert classify_functional_result(build_exit=0, oracle_exit=1, parsed_pass=False) == "FAIL"
    assert classify_functional_result(build_exit=0, oracle_exit=0, parsed_pass=True) == "PASS"
    log = "==1==ERROR: AddressSanitizer: heap-buffer-overflow\n #0 0x123 in parse /x.c:9:1\n #1 0x456 in run /y.c:2"
    result = classify_security_result(build_exit=0, pov_exit=1, log=log)
    assert result["classification"] == "PRESENT"
    assert result["frames"] == ["parse", "run"]
    assert classify_security_result(build_exit=0, pov_exit=0, log="ok")["classification"] == "ABSENT"
    assert classify_security_result(build_exit=1, pov_exit=1, log=log)["classification"] == "INFRA_BUILD_FAILURE"


def test_procedure_representation_and_source_ranking() -> None:
    a = procedure_representation("int f(int n) { if (n) return read(n); return 0; }")
    b = procedure_representation("int renamed(int count) { if (count) return read(count); return 0; }")
    unrelated = procedure_representation("void x(void) { write(); close(); }")
    assert procedure_similarity(a, b)["combined"] > procedure_similarity(a, unrelated)["combined"]
    candidates = [
        SourceCandidate("b" * 40, "b.c", 1, "S2", 0.9, 5),
        SourceCandidate("a" * 40, "a.c", 1, "S1", 0.5, 4),
        SourceCandidate("c" * 40, "c.c", 1, "S1", 0.4, 6),
    ]
    assert uniquely_selected(candidates, b_time=10) == candidates[1]
    tied = candidates + [SourceCandidate("d" * 40, "d.c", 2, "S1", 0.5, 3)]
    assert uniquely_selected(tied, b_time=10) is None


def test_memory_future_information_leakage_and_evidence_schema() -> None:
    context = {"repository": "https://example.invalid/r", "commit": "a" * 40, "path": "x.c", "symbol": "f", "source_date": "2020-01-01", "source_task": "parse records"}
    memory = render_source_memory(context, "int f(void) { return 0; }")
    assert not memory_leakage_findings(memory)
    with pytest.raises(ValueError, match="future-information leakage"):
        render_source_memory(context, "/* CVE-2020-1234 security fix */")
    review = {
        "schema": "securevibebench-development-review-v1",
        "answers": {f"Q{i}": {"answer": "UNKNOWN", "evidence": ["not-yet-measured"]} for i in range(1, 13)},
    }
    packet = {
        "schema": "securevibebench-development-evidence-v1",
        "instance_id": "26952",
        "bur": {},
        "task_matrix": {},
        "security_matrix": {},
        "source_candidates": [],
        "memory": memory,
        "review": review,
    }
    validate_evidence_packet(packet)
    packet["model_output"] = "forbidden"
    with pytest.raises(ValueError, match="topology"):
        validate_evidence_packet(packet)


def test_extract_crash_state_is_metadata_only_and_bounded() -> None:
    meta = {
        "report": {
            "comments": [
                {"content": "prefix\nCrash State:\n  first\n  second\n  third\n  fourth\n\nSanitizer: asan"}
            ]
        }
    }
    assert extract_crash_state(meta) == ["first", "second", "third"]

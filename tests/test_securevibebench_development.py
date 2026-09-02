import json
import importlib.util
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


def load_runner_module():
    path = ROOT / "scripts" / "run_securevibebench_seen_case.py"
    spec = importlib.util.spec_from_file_location("run_securevibebench_seen_case", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_official_duplicate_functional_script_mapping() -> None:
    config = json.loads((ROOT / "protocols" / "securevibebench-seen-cases.json").read_text())
    assert config["cases"]["11060"]["test_script_id"] == "11074"
    assert config["cases"]["11074"]["test_script_id"] == "11074"
    assert set(config["cases"]) == set(SEEN_IDS)


def test_benchmark_functional_comparison_semantics() -> None:
    runner = load_runner_module()
    assert runner.benchmark_compare(
        {"type": "BoolResult", "Status": False},
        {"type": "BoolResult", "Status": True},
    )["functional_pass"] is False
    assert runner.benchmark_compare(
        {"type": "ListResult", "PassList": ["a", "b"]},
        {"type": "ListResult", "PassList": ["a"]},
    )["functional_pass"] is True
    assert runner.benchmark_compare(
        {"type": "NumberResult"},
        {"type": "NumberResult"},
    )["functional_compare_error"] is True


def test_time_metrics_parser() -> None:
    runner = load_runner_module()
    metrics = runner.parse_time_metrics(
        "User time (seconds): 1.25\nMaximum resident set size (kbytes): 4096\n"
    )
    assert metrics == {"maximum_rss_kb": 4096, "user_seconds": 1.25}


def test_required_development_artifacts_and_readiness() -> None:
    root = ROOT / "artifacts" / "v2-securevibebench-development"
    required = {
        "development-report.md",
        "readiness.json",
        "source-lock.json",
        "seen-set-manifest.json",
        "unseen-universe.json",
        "schema-map.json",
        "container-feasibility.json",
        "bur-security-matrices.json",
        "task-completion-matrices.json",
        "source-retrieval-results.json",
        "source-threshold-calibration.json",
        "review-form.json",
        "deduplication-test.json",
        "runtime-costs.json",
        "prospective-protocol-recommendation.md",
    }
    assert required <= {path.name for path in root.iterdir()}
    readiness = json.loads((root / "readiness.json").read_text())
    assert readiness["seen_ids"] == list(SEEN_IDS)
    assert readiness["raw_task_count"] == 105
    assert readiness["unseen_task_count"] == 97
    assert readiness["deduplicated_unseen_count"] == 78
    assert readiness["prospective_protocol_ready"] is False
    assert readiness["gpu_needed_for_discovery"] is False


def test_real_bur_artifact_matches_seen_config() -> None:
    root = ROOT / "artifacts" / "v2-securevibebench-development"
    bur = json.loads((root / "bur-security-matrices.json").read_text())
    config = json.loads((ROOT / "protocols" / "securevibebench-seen-cases.json").read_text())["cases"]
    assert [case["instance_id"] for case in bur["cases"]] == list(SEEN_IDS)
    for case in bur["cases"]:
        expected = config[case["instance_id"]]
        assert case["ancestry"]["B"] == expected["B"]
        assert case["ancestry"]["U"] == expected["U"]
        assert case["ancestry"]["R"] == expected["R"]
        assert case["ancestry"]["u_parent_count"] == 1
        assert case["ancestry"]["u_is_ancestor_of_r"] is True


def test_artifacts_never_contain_unseen_implementation_evidence() -> None:
    root = ROOT / "artifacts" / "v2-securevibebench-development"
    universe = json.loads((root / "unseen-universe.json").read_text())
    assert set(universe) >= {"unseen_ids", "schema"}
    assert not ({"description", "diff", "patch", "source"} & set(universe))
    allowed_case_ids = set(SEEN_IDS)
    for filename, key in (
        ("bur-security-matrices.json", "cases"),
        ("task-completion-matrices.json", "cases"),
        ("source-retrieval-results.json", "cases"),
    ):
        data = json.loads((root / filename).read_text())
        assert {case["instance_id"] for case in data[key]} <= allowed_case_ids


def test_review_form_and_source_threshold_are_not_outcome_frozen() -> None:
    root = ROOT / "artifacts" / "v2-securevibebench-development"
    review = json.loads((root / "review-form.json").read_text())
    assert [item["id"] for item in review["questions"]] == [f"Q{i}" for i in range(1, 13)]
    assert review["model_output_allowed"] is False
    calibration = json.loads((root / "source-threshold-calibration.json").read_text())
    assert calibration["threshold_frozen"] is False
    assert calibration["recommended_threshold"] is None
    retrieval = json.loads((root / "source-retrieval-results.json").read_text())
    assert sum(case["eligible_source_count"] for case in retrieval["cases"]) == 0
    assert all(case["selected_source"] is None for case in retrieval["cases"])

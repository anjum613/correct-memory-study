from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest


RUNNER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNNER_ROOT))

import track_a_runner as legacy
import track_a_runner_v2 as runner


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _snapshot(
    *,
    position: int = 22,
    records: int = 21,
    action: str = "CONTINUE",
    head: str = "a" * 40,
) -> legacy.Snapshot:
    return legacy.Snapshot(
        head=head,
        records_published=records,
        successor_positions_processed=records,
        historical_unique_opened_anchors=2,
        global_unique_opened_anchors=19,
        final=0,
        categories_represented=0,
        next_due_position=position,
        global_action=action,
    )


class FakeRepository:
    def __init__(self, root: Path) -> None:
        self.worktree = root
        self.run_path = root / "run"
        self.run_path.mkdir()
        self.b_required = False
        self.invalid_a = False
        self.invalid_b = False
        self.completion_permitted = True

    def position_path(self, position: int) -> Path:
        return self.run_path / "positions" / f"{position:08d}"

    def discovery_materialization_ready(self) -> bool:
        return True

    def validate_materialized_position(self, position: int) -> None:
        assert position == 22

    def validate_tptm_bundle(self, position: int) -> None:
        assert position == 22

    def validate_review_packet(self, position: int) -> None:
        assert position == 22

    def validate_combined_review(self, position: int, path: Path) -> dict:
        assert position == 22
        return json.loads(path.read_text())

    def validate_family_metadata(
        self, position: int, path: Path, combined: object | None
    ) -> dict:
        assert position == 22
        return json.loads(path.read_text())

    def validate_executable_metadata(
        self, position: int, path: Path, family: object
    ) -> dict:
        assert position == 22
        return json.loads(path.read_text())

    def b_assignment_completion_permitted(self, path: Path, position: int) -> bool:
        return self.completion_permitted and position == 22 and path.is_file()

    def validate_assignment(self, path: Path, role: legacy.Role) -> dict:
        value = json.loads(path.read_text())
        invalid = self.invalid_a if role is legacy.Role.AI_FIRST_REVIEW else self.invalid_b
        if invalid or value.get("valid") is False:
            raise legacy.RunnerError("invalid assignment fixture")
        return value

    def validate_ai_decision(self, path: Path, role: legacy.Role) -> dict:
        value = json.loads(path.read_text())
        if value.get("valid") is False:
            raise legacy.RunnerError("invalid decision fixture")
        return value

    def latest_b_assignment(self, position: int) -> Path | None:
        root = self.position_path(position)
        candidates: list[tuple[int, Path]] = []
        base = root / "ai-reviewer-b-assignment.json"
        if base.exists():
            candidates.append((0, base))
        for path in root.glob("ai-reviewer-b-assignment-[0-9][0-9][0-9][0-9].json"):
            candidates.append((int(path.stem.rsplit("-", 1)[1]), path))
        return max(candidates, default=(0, None), key=lambda item: item[0])[1]

    def reviewer_b_requirement(self, position: int) -> tuple[bool, str, int]:
        return self.b_required, "FIXTURE_TRIGGER", 7


def _materialized(repository: FakeRepository, position: int = 22) -> Path:
    root = repository.position_path(position)
    _write(
        root / "position-authorization.json",
        {
            "schema": "candidate-screening-position-authorization-v0.2.0",
            "queue_position": position,
            f"position_{position + 1}_authorized": False,
        },
    )
    # Deliberately substantive-looking bytes: the classifier test below proves
    # they are never parsed.
    (root / "candidate-manifest.json").write_text(
        "THIS IS NOT JSON AND MUST NOT BE OPENED BY THE OUTER RUNNER\n",
        encoding="utf-8",
    )
    return root


def _routing(repository: FakeRepository, state: str) -> Path:
    root = _materialized(repository)
    _write(root / "tptm-run-envelope.json", {})
    _write(root / "tptm-result.json", {})
    _write(root / "hybrid-routing.json", {"queue_position": 22, "state": state})
    return root


def _review(repository: FakeRepository, *, b: bool = False, b_decision: bool = False) -> Path:
    root = _routing(repository, "STRUCTURED_REVIEW_REQUIRED")
    _write(root / "review-packet.json", {})
    _write(root / "ai-reviewer-a-assignment.json", {"valid": True})
    _write(root / "ai-reviewer-a-decision.json", {"valid": True})
    if b:
        _write(root / "ai-reviewer-b-assignment.json", {"valid": True})
    if b_decision:
        _write(root / "ai-reviewer-b-decision.json", {"valid": True})
    return root


SCENARIOS = [
    ("T01", "PRE_POSITION"),
    ("T03", "AUTO_MECHANICAL_TERMINAL"),
    ("T04", "OUT_OF_SCOPE_TERMINAL"),
    ("T07", "STRUCTURED_REVIEW_REQUIRED"),
    ("T08", "AI_FIRST_REVIEW_REQUIRED"),
    ("T12", "AI_SECOND_NOT_REQUIRED"),
    ("T13", "AI_SECOND_ASSIGNMENT_REQUIRED"),
    ("T14", "REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED"),
    ("T15", "COMBINATION_REQUIRED"),
    ("T19", "CONSTRAINED_FAMILY_FEASIBILITY_REQUIRED"),
    ("T20", "NO_UNIQUE_FOCAL_FAILURE"),
    ("T21", "EXECUTABLE_VALIDATION_REQUIRED"),
    ("T22", "CONSTRUCTION_FAILED"),
    ("T23", "FINAL_READY"),
    ("T24", "EXECUTABLE_VALIDATION_FAILED"),
]


@pytest.mark.parametrize(("scenario_id", "expected"), SCENARIOS)
def test_scenario_classifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_id: str,
    expected: str,
) -> None:
    repository = FakeRepository(tmp_path)
    classifier = runner.DurableClassifier(repository)  # type: ignore[arg-type]
    monkeypatch.setattr(classifier, "_due_is_administrative", lambda position: False)
    if scenario_id == "T01":
        pass
    elif scenario_id == "T03":
        _routing(repository, "AUTO_MECHANICAL_REJECT")
    elif scenario_id == "T04":
        _routing(repository, "OUT_OF_SCOPE_UNSUPPORTED")
    elif scenario_id == "T07":
        root = _routing(repository, "STRUCTURED_REVIEW_REQUIRED")
        _write(root / "review-packet.json", {})
    elif scenario_id == "T08":
        root = _routing(repository, "STRUCTURED_REVIEW_REQUIRED")
        _write(root / "review-packet.json", {})
        _write(root / "ai-reviewer-a-assignment.json", {"valid": True})
    elif scenario_id == "T12":
        _review(repository)
    elif scenario_id == "T13":
        repository.b_required = True
        _review(repository)
    elif scenario_id == "T14":
        repository.b_required = True
        root = _review(repository, b=True)
        _write(root / "ai-reviewer-b-assignment.json", {"valid": False})
    elif scenario_id == "T15":
        repository.b_required = True
        _review(repository, b=True, b_decision=True)
    else:
        repository.b_required = True
        root = _review(repository, b=True, b_decision=True)
        _write(
            root / "combined-review.json",
            {
                "combined_outcome": "REVIEW_UNRESOLVED",
                "authorized_next_action": "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION",
            },
        )
        if scenario_id == "T20":
            _write(
                root / "family-feasibility.json",
                {
                    "reason_code": "NO_UNIQUE_FOCAL_HYPOTHESIS_UNDER_FROZEN_DISAGREEMENT_POLICY",
                    "family_construction_state": "FAILED",
                },
            )
        elif scenario_id == "T21":
            _write(
                root / "family-feasibility.json",
                {
                    "family_construction_state": "SUCCEEDED",
                    "executable_validation_state": "PENDING",
                },
            )
        elif scenario_id == "T22":
            _write(
                root / "family-feasibility.json",
                {"family_construction_state": "FAILED", "reason_code": "OTHER"},
            )
        elif scenario_id == "T23":
            _write(
                root / "family-feasibility.json",
                {
                    "family_construction_state": "SUCCEEDED",
                    "executable_validation_state": "PASSED",
                    "admission_state": "ADMIT_FINAL",
                },
            )
            _write(
                root / "family-executable-validation.json",
                {"validation_state": "PASSED"},
            )
        elif scenario_id == "T24":
            _write(
                root / "family-feasibility.json",
                {
                    "family_construction_state": "SUCCEEDED",
                    "executable_validation_state": "FAILED",
                },
            )
            _write(
                root / "family-executable-validation.json",
                {"validation_state": "FAILED"},
            )
    assert classifier.classify(_snapshot()).state.value == expected


def test_administrative_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FakeRepository(tmp_path)
    classifier = runner.DurableClassifier(repository)  # type: ignore[arg-type]
    monkeypatch.setattr(classifier, "_due_is_administrative", lambda position: True)
    result = classifier.classify(_snapshot())
    assert result.state is runner.DurableState.ADMINISTRATIVE_TERMINAL
    assert result.next_role is legacy.Role.POSITION_CONTROLLER


@pytest.mark.parametrize(
    ("scenario_id", "outcome", "expected"),
    [
        ("T09", "REVIEW_REJECT", runner.DurableState.REVIEW_REJECT),
        ("T10", "REVIEW_RETAIN", runner.DurableState.CONSTRUCTION_REQUIRED),
        ("T11", "REVIEW_UNRESOLVED", runner.DurableState.REVIEW_UNRESOLVED),
    ],
)
def test_review_outcome_handlers(
    tmp_path: Path, scenario_id: str, outcome: str, expected: runner.DurableState
) -> None:
    repository = FakeRepository(tmp_path)
    repository.b_required = True
    root = _review(repository, b=True, b_decision=True)
    _write(
        root / "combined-review.json",
        {"combined_outcome": outcome, "authorized_next_action": "PUBLICATION"},
    )
    assert runner.DurableClassifier(repository).classify(_snapshot()).state is expected  # type: ignore[arg-type]


def _semantic(*, answer: str = "YES", focal: str = "P") -> dict:
    return {
        "candidate_id": "candidate",
        "review_packet_sha256": "a" * 64,
        "answers": [{"question_id": "Q1", "answer": answer}],
        "outcome": "REVIEW_RETAIN",
        "focal_hypothesis": {"predicate_type": focal},
    }


@pytest.mark.parametrize(
    ("scenario_id", "variant", "expected"),
    [
        ("T16", "agreement", ("REVIEW_RETAIN", "AGREEMENT")),
        (
            "T17",
            "semantic",
            ("REVIEW_UNRESOLVED", "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION"),
        ),
        (
            "T18",
            "focal",
            ("REVIEW_UNRESOLVED", "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION"),
        ),
    ],
)
def test_combination_policy(
    scenario_id: str, variant: str, expected: tuple[str, str]
) -> None:
    first = _semantic()
    second = _semantic(
        answer="NO" if variant == "semantic" else "YES",
        focal="C" if variant == "focal" else "P",
    )
    assert legacy.combine_review_metadata(first, second) == expected


def test_actual_position_22_blocker_regression() -> None:
    class Logger:
        def emit_event(self, *args: object, **kwargs: object) -> None:
            pass

    repository = runner.ProductionRepositoryV2(
        runner.DEFAULT_WORKTREE,
        runner.DEFAULT_RUNNER_ROOT,
        runner.DEFAULT_RUNNER_ROOT / "state/runner-state.json",
        Logger(),  # type: ignore[arg-type]
    )
    snapshot = repository._snapshot_at_actual_head()
    blocker = repository.position_path(22) / "autonomous-blocker.json"
    before = blocker.read_bytes()
    position = repository.position_path(22)
    decision = position / "ai-reviewer-a-decision.json"
    decision_before = decision.read_bytes()
    result = runner.DurableClassifier(repository).classify(snapshot)
    assert snapshot.records_published == 23
    assert snapshot.next_due_position == 24
    assert result.state is runner.DurableState.PRE_POSITION
    assert result.recovery_id == "CURRENT_POSITION_MATERIALIZATION"
    assert blocker.read_bytes() == before
    assert hashlib.sha256(before).hexdigest() == runner.BLOCKER_SHA256
    assert (position / "position-authorization.json").is_file()
    assert (position / "candidate-manifest.json").is_file()
    assert (position / "tptm-result.json").is_file()
    assert (position / "hybrid-routing.json").is_file()
    assert (position / "ai-reviewer-a-assignment.json").is_file()
    assert decision.read_bytes() == decision_before
    assert hashlib.sha256(decision_before).hexdigest() == (
        "06465e9f58a4d03ecaa09390b62571903ccb6e13edde73ae9cb9cc744c6c79ea"
    )
    assert (position / "ai-reviewer-b-decision.json").is_file()
    assert not (position / "terminal-record.json").exists()
    assert (repository.run_path / "records/00000022.json").is_file()
    assert repository.position_path(23).is_dir()
    assert not repository.position_path(24).exists()


@pytest.mark.parametrize(
    ("scenario_id", "recovery_id"),
    [("T06", "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING")],
)
def test_recovery_registry_entry(scenario_id: str, recovery_id: str) -> None:
    _matrix, registry = runner.validate_transition_definitions()
    rows = {row["id"]: row for row in registry["recoveries"]}
    assert rows[recovery_id]["failure_state"] == "BLOCKER"
    assert rows[recovery_id]["scientific_invariants_unchanged"]


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("T28", runner.DurableState.PRE_POSITION),
        ("T29", runner.DurableState.POSITION_MATERIALIZATION_REQUIRED),
        ("T30", runner.DurableState.DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED),
        ("T31", runner.DurableState.AI_SECOND_NOT_REQUIRED),
        ("T32", runner.DurableState.COMBINATION_REQUIRED),
    ],
)
def test_crash_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario_id: str,
    expected: runner.DurableState,
) -> None:
    repository = FakeRepository(tmp_path)
    classifier = runner.DurableClassifier(repository)  # type: ignore[arg-type]
    monkeypatch.setattr(classifier, "_due_is_administrative", lambda position: False)
    if scenario_id == "T29":
        production = runner.DEFAULT_WORKTREE / runner.RUN_RELATIVE_PATH / (
            "positions/00000022/autonomous-blocker.json"
        )
        destination = repository.position_path(22) / "autonomous-blocker.json"
        destination.parent.mkdir(parents=True)
        shutil.copyfile(production, destination)
    elif scenario_id == "T30":
        root = repository.position_path(22)
        _write(
            root / "position-authorization.json",
            {
                "schema": "candidate-screening-position-authorization-v0.2.0",
                "queue_position": 22,
                "position_23_authorized": False,
            },
        )
    elif scenario_id == "T31":
        _review(repository)
    elif scenario_id == "T32":
        repository.b_required = True
        _review(repository, b=True, b_decision=True)
    assert classifier.classify(_snapshot()).state is expected


def test_terminal_commit_restart() -> None:
    # A terminal commit whose external state update was interrupted is exactly the
    # valid-descendant recovery trigger; the next ledger boundary is authoritative.
    _matrix, registry = runner.validate_transition_definitions()
    recovery = next(
        item
        for item in registry["recoveries"]
        if item["id"] == "VALID_DESCENDANT_HEAD_RECONCILIATION"
    )
    assert recovery["success_state"] == "CLASSIFY_FROM_DURABLE_STATE"
    assert "external runner-state.json" in recovery["allowed_outputs"]


def test_valid_descendant_recovery_registered() -> None:
    _matrix, registry = runner.validate_transition_definitions()
    assert "VALID_DESCENDANT_HEAD_RECONCILIATION" in {
        item["id"] for item in registry["recoveries"]
    }


def _git(path: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def test_unexplained_head_fails_closed(tmp_path: Path) -> None:
    worktree = tmp_path / "git"
    worktree.mkdir()
    _git(worktree, "init")
    _git(worktree, "config", "user.email", "fixture@example.invalid")
    _git(worktree, "config", "user.name", "Fixture")
    (worktree / "README").write_text("one", encoding="utf-8")
    _git(worktree, "add", "README")
    _git(worktree, "commit", "-m", "one")
    first = _git(worktree, "rev-parse", "HEAD")
    (worktree / "README").write_text("two", encoding="utf-8")
    _git(worktree, "commit", "-am", "two")
    repository = object.__new__(runner.ProductionRepositoryV2)
    repository.worktree = worktree
    repository.state = {"expected_head": first}
    repository.logger = SimpleNamespace(emit_event=lambda *args, **kwargs: None)
    with pytest.raises(runner.RunnerError, match="unexplained paths"):
        repository._reconcile_expected_head(
            _snapshot(head=_git(worktree, "rev-parse", "HEAD"))
        )


def _minimal_snapshot_repository(tmp_path: Path) -> runner.ProductionRepositoryV2:
    repository = object.__new__(runner.ProductionRepositoryV2)
    repository.worktree = tmp_path
    repository.run_path = tmp_path / "run"
    repository.run_path.mkdir()
    repository.ledger_path = repository.run_path / "ledger.json"
    repository.ledger_sidecar_path = repository.run_path / "ledger.json.sha256"
    repository.state = {"expected_head": "a" * 40}
    repository.actual_head = lambda: "a" * 40  # type: ignore[method-assign]
    repository._replay_ledger = lambda ledger, records: None  # type: ignore[method-assign]
    repository._verify_amended_terminal_record = lambda position, record: None  # type: ignore[method-assign]
    return repository


def _valid_empty_ledger() -> dict:
    return {
        "records_published": 0,
        "record_paths": [],
        "state": {
            "records_published": 0,
            "successor_positions_processed": 0,
            "historical_unique_opened_anchors": 2,
            "global_unique_opened_anchors": 2,
            "FINAL": 0,
            "trust_categories_represented": 0,
            "next_due_position": 1,
            "global_action": "CONTINUE",
        },
    }


def test_corrupted_ledger_fails(tmp_path: Path) -> None:
    repository = _minimal_snapshot_repository(tmp_path)
    _write(repository.ledger_path, {"records_published": "corrupt", "record_paths": []})
    digest = runner.sha256_file(repository.ledger_path)
    repository.ledger_sidecar_path.write_text(f"{digest}  ledger.json\n", encoding="ascii")
    with pytest.raises(runner.RunnerError, match="publication sequence"):
        repository._snapshot_at_actual_head()


def test_bad_checksum_fails(tmp_path: Path) -> None:
    repository = _minimal_snapshot_repository(tmp_path)
    _write(repository.ledger_path, _valid_empty_ledger())
    repository.ledger_sidecar_path.write_text(f"{'0' * 64}  ledger.json\n", encoding="ascii")
    with pytest.raises(legacy.RunnerError, match="sidecar mismatch"):
        repository._snapshot_at_actual_head()


def test_partial_publication_classification(tmp_path: Path) -> None:
    repository = FakeRepository(tmp_path)
    _write(repository.run_path / "records/00000022.json", {"queue_position": 22})
    result = runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]
    assert result.state is runner.DurableState.PARTIAL_PUBLICATION_RECONCILIATION
    assert result.recovery_id == "INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION"


def test_invalid_ai_a_fails(tmp_path: Path) -> None:
    repository = FakeRepository(tmp_path)
    root = _routing(repository, "STRUCTURED_REVIEW_REQUIRED")
    _write(root / "review-packet.json", {})
    _write(root / "ai-reviewer-a-assignment.json", {"valid": False})
    with pytest.raises(runner.RunnerError, match="AI-A assignment invalid"):
        runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]


def test_invalid_ai_b_requires_correction(tmp_path: Path) -> None:
    repository = FakeRepository(tmp_path)
    repository.b_required = True
    root = _review(repository, b=True)
    _write(root / "ai-reviewer-b-assignment.json", {"valid": False})
    result = runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]
    assert result.state is runner.DurableState.REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED


def test_blinding_violation_fails(tmp_path: Path) -> None:
    repository = FakeRepository(tmp_path)
    repository.b_required = True
    repository.invalid_b = True
    repository.completion_permitted = False
    _review(repository, b=True)
    with pytest.raises(runner.RunnerError, match="not mechanically correctable"):
        runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]


@pytest.mark.parametrize("future_position", [23, 24])
def test_future_position_isolation(tmp_path: Path, future_position: int) -> None:
    repository = FakeRepository(tmp_path)
    repository.position_path(future_position).mkdir(parents=True)
    with pytest.raises(runner.RunnerError, match="future-position isolation"):
        runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]


def test_lock_contention(tmp_path: Path) -> None:
    lock = tmp_path / "track-a-runner.lock"
    with lock.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner._lock_status(tmp_path) == "HELD"


def test_launcher_executes_runner_as_flock_owner() -> None:
    launcher = (runner.RUNNER_ROOT / "run-track-a.fish").read_text(
        encoding="utf-8"
    )
    assert "flock --exclusive --nonblock --no-fork" in launcher


def test_external_runner_lock_owner_is_discoverable() -> None:
    lock = runner.RUNNER_ROOT / "track-a-runner.lock"
    with lock.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        observation = runner._lock_observation(runner.RUNNER_ROOT)
        assert observation.status == "HELD"
        assert observation.owner_lookup_available is True
        assert os.getpid() in observation.owner_pids


def test_watchdog_reports_disappeared_child(tmp_path: Path) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "watchdog")
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.heartbeat = heartbeat
    executor.model = "fixture"
    executor.profile = None
    role_dir = tmp_path / "role"
    role_dir.mkdir()
    execution = executor._run_process(
        ["bash", "-c", "kill -TERM $$"],
        cwd=tmp_path,
        role=legacy.Role.POSITION_CONTROLLER,
        position=22,
        prompt="fixture\n",
        prompt_digest="a" * 64,
        invocation_id="fixture",
        started=runner.utc_now(),
        role_dir=role_dir,
        last_message_path=None,
    )
    assert execution.exit_code < 0
    assert (role_dir / "stdout.jsonl").is_file()
    assert (role_dir / "stderr.txt").is_file()
    heartbeat_value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert heartbeat_value["child_pid"] is None


def test_heartbeat_running(tmp_path: Path) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "running")
    heartbeat.update_snapshot(_snapshot())
    heartbeat.set_role("AI_FIRST_REVIEW", os.getpid())
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["status"] == "RUNNING"
    assert value["child_pid"] == os.getpid()
    assert value["position"] == 22
    assert value["role"] == "AI_FIRST_REVIEW"
    assert value["current_position"] == 22
    assert value["current_role"] == "AI_FIRST_REVIEW"


def test_heartbeat_stopped(tmp_path: Path) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "stopped")
    heartbeat.set_role("POSITION_CONTROLLER", os.getpid())
    heartbeat.stopped("finished")
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["status"] == "STOPPED"
    assert value["runner_pid"] is None
    assert value["child_pid"] is None
    assert value["last_runner_pid"] == os.getpid()
    assert value["last_child_pid"] == os.getpid()


def test_status_running(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "status-running")
    heartbeat.update_snapshot(_snapshot())
    heartbeat.set_role("AI_FIRST_REVIEW", os.getpid())
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: RUNNING" in output
    assert f"RUNNER_PID: {os.getpid()}" in output
    assert "ROLE: AI_FIRST_REVIEW" in output
    assert "NEXT_DUE_POSITION: 22" in output


def test_status_stopped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "status-stopped")
    heartbeat.stopped("clean stop")
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: STOPPED" in output
    assert "RUNNER_PID: -" in output
    assert "CHILD_PID: -" in output
    assert "LAST_REASON: clean stop" in output


def test_status_running_dead_pid_is_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path / "state/heartbeat.json",
        {
            "schema": runner.HEARTBEAT_SCHEMA,
            "status": "RUNNING",
            "runner_pid": 2_000_000_000,
            "child_pid": None,
            "last_runner_pid": 2_000_000_000,
            "last_child_pid": None,
            "heartbeat_timestamp": runner.utc_now(),
        },
    )
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: STALE" in output
    assert "RUNNER_PID: -" in output
    assert "RECORDED_RUNNER_PID: 2000000000" in output
    assert "REASON: heartbeat says RUNNING but runner process is absent" in output


def test_status_stopped_legacy_stale_pids_are_historical_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path / "state/heartbeat.json",
        {
            "schema": "track-a-runner-heartbeat-v0.1",
            "status": "STOPPED",
            "runner_pid": 3_044_960,
            "child_pid": 2_000_000_000,
            "heartbeat_timestamp": runner.utc_now(),
            "position": 22,
        },
    )
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: STOPPED" in output
    assert "RUNNER_PID: -" in output
    assert "CHILD_PID: -" in output
    assert "LAST_RUNNER_PID: 3044960" in output
    assert "LAST_CHILD_PID: 2000000000" in output
    assert "STATUS: RUNNING" not in output


def test_status_reports_disappeared_child_without_claiming_it_live(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path / "state/heartbeat.json",
        {
            "schema": runner.HEARTBEAT_SCHEMA,
            "status": "RUNNING",
            "runner_pid": os.getpid(),
            "child_pid": 2_000_000_000,
            "last_runner_pid": os.getpid(),
            "last_child_pid": 2_000_000_000,
            "heartbeat_timestamp": runner.utc_now(),
        },
    )
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: RUNNING" in output
    assert "CHILD_PID: -" in output
    assert "RECORDED_CHILD_PID: 2000000000" in output
    assert "CHILD_STATUS: DISAPPEARED" in output
    assert "durable reconciliation pending" in output


def test_status_is_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "read-only-status")
    heartbeat.stopped("fixture")
    before = {
        str(path.relative_to(tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert runner.status_command(tmp_path) == 0
    capsys.readouterr()
    after = {
        str(path.relative_to(tmp_path)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_heartbeat_normalization_is_external_only(tmp_path: Path) -> None:
    runner_root = tmp_path / "runner"
    production = tmp_path / "production"
    _write(production / "sentinel.json", {"scientific": "unchanged"})
    _write(
        runner_root / "state/heartbeat.json",
        {
            "schema": "track-a-runner-heartbeat-v0.1",
            "status": "STOPPED",
            "runner_pid": 3_044_960,
            "child_pid": 2_000_000_000,
            "runner_id": "historical",
            "position": 22,
            "production_head": "a" * 40,
            "last_event": "DRY_RUN",
            "last_event_timestamp": "2026-08-29T01:05:52Z",
            "heartbeat_timestamp": "2026-08-29T01:05:52Z",
            "last_classification": "POSITION_MATERIALIZATION_REQUIRED",
            "last_reason": "dry run complete",
        },
    )
    production_before = hashlib.sha256(
        (production / "sentinel.json").read_bytes()
    ).hexdigest()
    result = runner.normalize_heartbeat_state(runner_root)
    value = json.loads((runner_root / "state/heartbeat.json").read_text())
    assert result["result"] == "NORMALIZED"
    assert value["schema"] == runner.HEARTBEAT_SCHEMA
    assert value["status"] == "STOPPED"
    assert value["runner_pid"] is None
    assert value["child_pid"] is None
    assert value["last_runner_pid"] == 3_044_960
    assert value["last_child_pid"] == 2_000_000_000
    assert value["runner_id"] == "historical"
    assert value["position"] == 22
    assert value["production_head"] == "a" * 40
    assert value["last_event"] == "DRY_RUN"
    assert value["last_event_timestamp"] == "2026-08-29T01:05:52Z"
    assert value["heartbeat_timestamp"] == "2026-08-29T01:05:52Z"
    assert value["last_classification"] == "POSITION_MATERIALIZATION_REQUIRED"
    assert value["last_reason"] == "dry run complete"
    assert hashlib.sha256((production / "sentinel.json").read_bytes()).hexdigest() == (
        production_before
    )
    assert runner.normalize_heartbeat_state(runner_root)["result"] == (
        "ALREADY_NORMALIZED"
    )


def test_events_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "events")
    logger = runner.StructuredLogger(tmp_path, "events", heartbeat)
    logger.emit_event(
        runner.EventType.DURABLE_STATE_CLASSIFIED,
        position=22,
        role="POSITION_CONTROLLER",
        durable_state="TPTM_REQUIRED",
        reason="fixture",
    )
    assert runner.events_command(tmp_path, 10) == 0
    output = capsys.readouterr().out
    assert "DURABLE_STATE_CLASSIFIED" in output
    assert "position=22" in output
    assert "state=TPTM_REQUIRED" in output


class DoctorRepository:
    def __init__(self, worktree: Path, root: Path, state: Path, logger: object) -> None:
        self.worktree = worktree
        self.run_path = worktree / "run"
        self.state = {"expected_head": "a" * 40}

    def branch(self) -> str:
        return runner.EXPECTED_BRANCH

    def _verify_amendment_chain(self) -> dict:
        return {"valid": True, "external_runner_artifacts": []}

    def _snapshot_at_actual_head(self) -> legacy.Snapshot:
        return _snapshot()

    def position_path(self, position: int) -> Path:
        return self.run_path / "positions" / f"{position:08d}"


def _valid_reachable_recovery_inputs(*args: object) -> dict[str, object]:
    return {
        "check": "CURRENT_POSITION_MATERIALIZATION_INPUTS",
        "tree_sha256": "a" * 64,
        "writes_performed": False,
    }


def _passing_network_probe(role: legacy.Role) -> runner.review_network.SandboxNetworkProbe:
    return runner.review_network.SandboxNetworkProbe(
        passed=True,
        role=role.value,
        resolver_mode="FIXTURE",
        resolver_target="/run/systemd/resolve/stub-resolv.conf",
        dns_status="PASS",
        https_status="403",
        retryable=False,
        reason="fixture pass",
    )


def _codex_fixture(path: Path, *, version: str = "codex-cli 0.150.1") -> Path:
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        f"  echo '{version}'\n"
        "else\n"
        "  echo '--json --ephemeral --ignore-user-config --color "
        "--dangerously-bypass-approvals-and-sandbox --model --cd "
        "--output-schema --output-last-message'\n"
        "fi\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _doctor_fixture(tmp_path: Path, *, materializer: bool) -> Path:
    worktree = tmp_path / "worktree"
    (worktree / "src").parent.mkdir(parents=True, exist_ok=True)
    (worktree / "src").symlink_to(runner.DEFAULT_WORKTREE / "src", target_is_directory=True)
    blocker_source = runner.DEFAULT_WORKTREE / runner.RUN_RELATIVE_PATH / (
        "positions/00000022/autonomous-blocker.json"
    )
    blocker = worktree / "run/positions/00000022/autonomous-blocker.json"
    blocker.parent.mkdir(parents=True)
    shutil.copyfile(blocker_source, blocker)
    provisioning = worktree / "scripts/provision_frozen_discovery_artifacts.py"
    provisioning.parent.mkdir(parents=True, exist_ok=True)
    provisioning.write_text("# fixture\n", encoding="utf-8")
    executable_schema = worktree / runner.NEW_AMENDMENT_RELATIVE_PATH / (
        "family-executable-validation.schema.json"
    )
    executable_schema.parent.mkdir(parents=True, exist_ok=True)
    executable_schema.write_text("{}\n", encoding="utf-8")
    provider_source = (
        runner.DEFAULT_WORKTREE / runner.STRUCTURED_OUTPUT_CORRECTION_RELATIVE_PATH
    )
    provider_target = worktree / runner.STRUCTURED_OUTPUT_CORRECTION_RELATIVE_PATH
    provider_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(provider_source, provider_target)
    if materializer:
        target = worktree / runner.MATERIALIZER_RELATIVE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")
    return worktree


def test_doctor_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    result = runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    )
    assert result == 0
    output = capsys.readouterr().out
    expected_checks = {
        "TRANSITION_AND_RECOVERY_DEFINITIONS",
        "TRANSITION_TEST_COVERAGE",
        "RUNNER_LOCK",
        "CODEX_CLI_PRESENT",
        "CODEX_CLI_VERSION_AND_EXEC_OPTIONS",
        "AI_REVIEW_OUTPUT_SCHEMA_COMPATIBILITY",
        "AI_FIRST_REVIEW_OUTPUT_SCHEMA",
        "AI_SECOND_REVIEW_OUTPUT_SCHEMA",
        "PROVIDER_TO_CANONICAL_PROJECTION",
        "RUNNER_STATE",
        "AI_FIRST_REVIEW_EVIDENCE_REFERENCE_CONTRACT",
        "AI_SECOND_REVIEW_EVIDENCE_REFERENCE_CONTRACT",
        "PRODUCTION_BRANCH",
        "FROZEN_AMENDMENT_HASHES",
        "EXTERNAL_RUNNER_HASHES",
        "LEDGER_CHECKSUM_AND_REPLAY",
        "PRODUCTION_HEAD",
        "CURRENT_DURABLE_CLASSIFICATION",
        "TRANSITION_HANDLER_COVERAGE",
        "MATERIALIZATION_INTERFACE",
            "CURRENT_REACHABLE_INTERFACE",
            "CURRENT_POSITION_MATERIALIZATION_INPUTS",
            "REVIEW_SANDBOX_NETWORK_PREFLIGHT",
            "HEARTBEAT_STATUS_EVENTS",
        "HEARTBEAT_LIFECYCLE",
    }
    observed_checks = {
        line.split(":", 2)[1].strip()
        for line in output.splitlines()
        if line.startswith(("PASS: ", "FAIL: "))
    }
    assert observed_checks == expected_checks
    assert all(
        line.startswith("PASS: ")
        for line in output.splitlines()
        if line.startswith(("PASS: ", "FAIL: "))
    )
    assert "DOCTOR: PASS" in output
    assert "FAILED_CHECK_COUNT: 0" in output
    assert "FAILED_CHECKS: []" in output


def test_doctor_detects_old_provider_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    old_schema = (
        runner.DEFAULT_WORKTREE
        / legacy.AMENDMENT_RELATIVE_PATH
        / legacy.AI_OUTPUT_SCHEMA
    )
    target = (
        worktree
        / runner.STRUCTURED_OUTPUT_CORRECTION_RELATIVE_PATH
        / legacy.AI_PROVIDER_OUTPUT_SCHEMA
    )
    shutil.copyfile(old_schema, target)
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    result = runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    )
    assert result == 1
    output = capsys.readouterr().out
    assert "FAIL: AI_REVIEW_OUTPUT_SCHEMA_COMPATIBILITY:" in output
    assert "unsupported schema keyword" in output


def test_provider_schema_is_identical_for_ai_a_and_blinded_ai_b() -> None:
    first = runner.validate_provider_output_schema_for_role(
        runner.DEFAULT_WORKTREE, legacy.Role.AI_FIRST_REVIEW
    )
    second = runner.validate_provider_output_schema_for_role(
        runner.DEFAULT_WORKTREE, legacy.Role.AI_SECOND_REVIEW
    )
    assert first["schema_path"] == second["schema_path"]
    assert first["schema_sha256"] == second["schema_sha256"]
    assert first["profile_sha256"] == second["profile_sha256"]
    assert first["role"] == "AI_FIRST_REVIEW"
    assert second["role"] == "AI_SECOND_REVIEW"


@pytest.mark.parametrize(
    "role", [legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW]
)
def test_provider_incompatibility_stops_before_network_or_child_launch(
    role: legacy.Role, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor = object.__new__(runner.CodexRoleExecutorV2)
    monkeypatch.setattr(
        executor,
        "verify_reviewer_output_schema",
        lambda actual_role: (_ for _ in ()).throw(
            legacy.RunnerError(f"old allOf schema for {actual_role.value}")
        ),
    )
    monkeypatch.setattr(
        runner,
        "wait_for_reviewer_network",
        lambda **kwargs: pytest.fail("network preflight must not run"),
    )
    with pytest.raises(
        runner.ProviderOutputSchemaIncompatible, match="old allOf schema"
    ):
        executor._execute_isolated_reviewer(
            role,
            22,
            "synthetic prompt",
            "a" * 64,
            "synthetic-invocation",
            runner.utc_now(),
            tmp_path,
            None,
            None,
        )


def test_invalid_json_schema_is_interface_blocker_without_network_retry() -> None:
    failure = (
        '{"type":"error","error":{"type":"invalid_request_error",'
        '"code":"invalid_json_schema","message":"Invalid schema for response_format '
        "'codex_output_schema': In context=(), 'allOf' is not permitted."
        '"param":"text.format.schema"},"status":400}'
    )
    assert runner.is_invalid_provider_schema_failure(failure, "")
    assert not runner.invalid_provider_schema_allows_retry()
    assert not any(
        pattern in failure.lower() for pattern in runner.NETWORK_TRANSPORT_PATTERNS
    )


def test_evidence_reference_contract_failure_is_not_a_network_retry() -> None:
    failure = (
        "provider focal_evidence_refs is empty; focal evidence is required"
    )
    assert not runner.evidence_reference_contract_allows_retry()
    assert not any(
        pattern in failure.lower() for pattern in runner.NETWORK_TRANSPORT_PATTERNS
    )


def test_position_22_ai_a_contract_uses_the_assignment_packet_only() -> None:
    class Logger:
        run_dir = runner.DEFAULT_RUNNER_ROOT / "logs/contract-test-read-only"

        def emit_event(self, *args: object, **kwargs: object) -> None:
            return None

    repository = runner.ProductionRepositoryV2(
        runner.DEFAULT_WORKTREE,
        runner.DEFAULT_RUNNER_ROOT,
        runner.DEFAULT_RUNNER_ROOT / "state/runner-state.json",
        Logger(),  # type: ignore[arg-type]
    )
    result = runner.validate_assignment_evidence_contract(
        repository,
        legacy.Role.AI_FIRST_REVIEW,
        repository.position_path(22) / "ai-reviewer-a-assignment.json",
    )
    assert result["allowed_evidence_refs"] == ["position-22-authorization"]
    assert result["canonical_order_source"].startswith(
        "ReviewPacket.evidence_index order"
    )


def test_blinded_ai_b_contract_uses_no_ai_a_material() -> None:
    result = runner.validate_synthetic_assignment_contract(
        runner.DEFAULT_WORKTREE, legacy.Role.AI_SECOND_REVIEW
    )
    assert result["role"] == "AI_SECOND_REVIEW"
    assert result["allowed_evidence_refs"] == ["synthetic-blinded-b-evidence"]
    assert result["ai_a_material_loaded"] is False


@pytest.mark.parametrize(
    "role", [legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW]
)
def test_evidence_contract_preflight_stops_before_network_or_child_launch(
    role: legacy.Role, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executor = object.__new__(runner.CodexRoleExecutorV2)
    monkeypatch.setattr(
        executor,
        "verify_reviewer_output_schema",
        lambda actual_role, assignment: (_ for _ in ()).throw(
            legacy.ProviderEvidenceReferenceContractError(
                f"invalid evidence contract for {actual_role.value}"
            )
        ),
    )
    monkeypatch.setattr(
        runner,
        "wait_for_reviewer_network",
        lambda **kwargs: pytest.fail("network preflight must not run"),
    )
    with pytest.raises(
        runner.ProviderEvidenceReferenceContractIncompatible,
        match="invalid evidence contract",
    ):
        executor._execute_isolated_reviewer(
            role,
            22,
            "synthetic prompt",
            "a" * 64,
            "synthetic-invocation",
            runner.utc_now(),
            tmp_path,
            tmp_path / "assignment.json",
            {"reviewer_role": role.value},
        )


def test_invalid_json_schema_execution_is_not_retried(tmp_path: Path) -> None:
    class SchemaFailureRepository:
        def __init__(self, root: Path) -> None:
            self.run_path = root / "run"
            self.run_path.mkdir()
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")
            self.state = {"expected_head": "a" * 40}

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot()

        def _snapshot_at_actual_head(self) -> legacy.Snapshot:
            return self.snapshot()

        def durable_token(self, position: int) -> legacy.DurableToken:
            return legacy.DurableToken("a" * 40, "p", "l", "t")

        def actual_head(self) -> str:
            return "a" * 40

        def position_path(self, position: int) -> Path:
            return self.run_path / "positions" / f"{position:08d}"

    class SchemaFailureExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(
            self, role: legacy.Role, position: int, expected_head: str
        ) -> legacy.RoleExecution:
            self.calls += 1
            return legacy.RoleExecution(
                role=role,
                position=position,
                invocation_id=f"schema-failure-{self.calls}",
                started_at_utc=runner.utc_now(),
                ended_at_utc=runner.utc_now(),
                exit_code=1,
                stdout="invalid_json_schema text.format.schema",
                stderr="",
                prompt="synthetic",
                prompt_sha256="a" * 64,
                infrastructure_failure=runner.INVALID_PROVIDER_SCHEMA_FAILURE,
            )

    class SchemaFailureClassifier:
        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            return runner.Classification(
                runner.DurableState.AI_FIRST_REVIEW_REQUIRED,
                "fixture schema failure",
                legacy.Role.AI_FIRST_REVIEW,
            )

    repository = SchemaFailureRepository(tmp_path)
    executor = SchemaFailureExecutor()
    logger = EventCollector(tmp_path)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = SchemaFailureClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.BLOCKER
    assert executor.calls == 1
    blocker = [fields for event, fields in logger.events if event is runner.EventType.BLOCKER]
    assert blocker[-1]["blocker_category"] == "ENGINEERING_BLOCKER"
    assert blocker[-1]["blocker_code"] == "PROVIDER_OUTPUT_SCHEMA_REJECTED"


def test_invalid_evidence_reference_execution_is_not_network_retried(
    tmp_path: Path,
) -> None:
    class EvidenceFailureRepository:
        def __init__(self, root: Path) -> None:
            self.run_path = root / "run"
            self.run_path.mkdir()
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")
            self.state = {"expected_head": "a" * 40}

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot()

        def _snapshot_at_actual_head(self) -> legacy.Snapshot:
            return self.snapshot()

        def durable_token(self, position: int) -> legacy.DurableToken:
            return legacy.DurableToken("a" * 40, "p", "l", "t")

        def actual_head(self) -> str:
            return "a" * 40

        def position_path(self, position: int) -> Path:
            return self.run_path / "positions" / f"{position:08d}"

        def accept_reviewer(
            self, execution: legacy.RoleExecution, before: legacy.DurableToken
        ) -> None:
            raise legacy.ProviderEvidenceReferenceContractError(
                "provider focal_evidence_refs is empty"
            )

    class EvidenceFailureExecutor:
        def __init__(self) -> None:
            self.calls = 0

        def execute(
            self, role: legacy.Role, position: int, expected_head: str
        ) -> legacy.RoleExecution:
            self.calls += 1
            return legacy.RoleExecution(
                role=role,
                position=position,
                invocation_id=f"evidence-failure-{self.calls}",
                started_at_utc=runner.utc_now(),
                ended_at_utc=runner.utc_now(),
                exit_code=0,
                stdout="synthetic structured output",
                stderr="",
                prompt="synthetic",
                prompt_sha256="a" * 64,
            )

    class EvidenceFailureClassifier:
        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            return runner.Classification(
                runner.DurableState.AI_FIRST_REVIEW_REQUIRED,
                "fixture evidence failure",
                legacy.Role.AI_FIRST_REVIEW,
            )

    repository = EvidenceFailureRepository(tmp_path)
    executor = EvidenceFailureExecutor()
    logger = EventCollector(tmp_path)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = EvidenceFailureClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.BLOCKER
    assert executor.calls == 1
    blocker = [
        fields for event, fields in logger.events if event is runner.EventType.BLOCKER
    ]
    assert blocker[-1]["blocker_category"] == "ENGINEERING_BLOCKER"
    assert blocker[-1]["blocker_code"] == (
        "PROVIDER_EVIDENCE_REFERENCE_CONTRACT_INVALID"
    )


def test_doctor_catches_reachable_candidate_pool_hash_mismatch_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )

    def mismatch(*args: object) -> dict[str, object]:
        raise runner.RunnerError(
            "error_code=ARTIFACT_HASH_MISMATCH artifact=/fixture/candidate-pool.jsonl "
            f"expected_sha256={'a' * 64} actual_sha256={'b' * 64}"
        )

    assert runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=mismatch,
        network_probe=_passing_network_probe,
    ) == 1
    output = capsys.readouterr().out
    assert "PASS: MATERIALIZATION_INTERFACE:" in output
    assert "PASS: CURRENT_REACHABLE_INTERFACE:" in output
    assert "FAIL: CURRENT_POSITION_MATERIALIZATION_INPUTS:" in output
    assert "error_code=ARTIFACT_HASH_MISMATCH" in output
    assert "expected_sha256=" + "a" * 64 in output
    assert "actual_sha256=" + "b" * 64 in output
    assert "DOCTOR: FAIL" in output


def test_canonical_codex_works_when_path_lacks_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _codex_fixture(tmp_path / "codex")
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", executable)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    result = runner.verify_codex_cli(None, tmp_path)
    assert result["path"] == str(executable.resolve())
    assert result["version"] == runner.EXPECTED_CODEX_VERSION


def test_canonical_codex_post_reboot_minimal_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _codex_fixture(tmp_path / "codex")
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", executable)
    monkeypatch.setattr(
        legacy,
        "sanitized_environment",
        lambda: {"HOME": str(tmp_path), "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    result = runner.verify_codex_cli(None, tmp_path)
    assert result["path"] == str(executable.resolve())
    assert result["status"] == "PASS"


def test_canonical_codex_missing_reports_full_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-codex"
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", missing)
    with pytest.raises(runner.RunnerError) as raised:
        runner.resolve_canonical_codex_executable()
    message = str(raised.value)
    assert f"attempted_executable_path={missing}" in message
    assert "exists=false" in message
    assert "executable=false" in message
    assert "version_check_status=NOT_RUN" in message
    assert "exact_os_error=FileNotFoundError:" in message


def test_canonical_codex_not_executable_reports_full_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _codex_fixture(tmp_path / "codex")
    executable.chmod(0o644)
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", executable)
    with pytest.raises(runner.RunnerError) as raised:
        runner.resolve_canonical_codex_executable()
    message = str(raised.value)
    assert "exists=true" in message
    assert "regular=true" in message
    assert "executable=false" in message
    assert "exact_os_error=NOT_A_REGULAR_EXECUTABLE" in message


def test_canonical_codex_wrong_version_reports_full_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _codex_fixture(tmp_path / "codex", version="codex-cli 0.149.0")
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", executable)
    with pytest.raises(runner.RunnerError) as raised:
        runner.verify_codex_cli(None, tmp_path)
    message = str(raised.value)
    assert f"attempted_executable_path={executable}" in message
    assert "version_check_status=FAIL(expected=codex-cli 0.150.1,observed=codex-cli 0.149.0)" in message
    assert "exact_os_error=NONE" in message


def test_doctor_and_role_executor_share_one_canonical_codex_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _codex_fixture(tmp_path / "codex")
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", executable)
    doctor_identity = runner.verify_codex_cli(None, tmp_path)
    role_identity = runner.resolve_canonical_codex_executable()
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.codex_bin = role_identity
    assert doctor_identity["path"] == str(executor.codex_bin)


def test_noncanonical_codex_override_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = _codex_fixture(tmp_path / "frozen-codex")
    other = _codex_fixture(tmp_path / "other-codex")
    monkeypatch.setattr(runner, "FROZEN_CODEX_EXECUTABLE", frozen)
    with pytest.raises(runner.RunnerError, match="FROZEN_PATH_MISMATCH"):
        runner.resolve_canonical_codex_executable(other)


def test_launcher_injects_frozen_codex_path_for_every_mode() -> None:
    source = (RUNNER_ROOT / "run-track-a.fish").read_text(encoding="utf-8")
    assert "set -l canonical_codex /home/anjum/.local/npm/bin/codex" in source
    assert "set -l runner_argv --codex-bin $canonical_codex $argv" in source
    assert source.count("$runner_argv") == 2


def test_doctor_catches_missing_materializer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=False)
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    result = runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    )
    assert result != 0
    output = capsys.readouterr().out
    assert (
        "FAIL: MATERIALIZATION_INTERFACE: exception=RunnerError: materializer missing"
        in output
    )
    assert "DOCTOR: FAIL" in output
    assert "FAILED_CHECK_COUNT: 2" in output
    assert (
        "FAILED_CHECKS:\n- TRANSITION_HANDLER_COVERAGE: "
        "exception=RunnerError: registered deterministic interface is absent: "
        f"{worktree / runner.MATERIALIZER_RELATIVE_PATH}\n"
        "- MATERIALIZATION_INTERFACE: "
        "exception=RunnerError: materializer missing"
    ) in output
    fail_lines = [line for line in output.splitlines() if line.startswith("FAIL: ")]
    assert fail_lines == [
        "FAIL: TRANSITION_HANDLER_COVERAGE: exception=RunnerError: registered "
        f"deterministic interface is absent: {worktree / runner.MATERIALIZER_RELATIVE_PATH}",
        "FAIL: MATERIALIZATION_INTERFACE: exception=RunnerError: materializer missing",
    ]
    assert output.index(fail_lines[0]) < output.index("DOCTOR: FAIL")


def test_doctor_names_legacy_stale_heartbeat_and_normalization_restores_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    _write(
        tmp_path / "state/heartbeat.json",
        {
            "schema": "track-a-runner-heartbeat-v0.1",
            "status": "STOPPED",
            "runner_pid": 3_044_960,
            "child_pid": None,
            "heartbeat_timestamp": runner.utc_now(),
            "position": 22,
        },
    )
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    assert runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    ) == 1
    before = capsys.readouterr().out
    assert "FAIL: HEARTBEAT_LIFECYCLE:" in before
    assert "stale_active_fields=runner_pid=3044960" in before
    assert "FAILED_CHECK_COUNT: 1" in before
    assert runner.normalize_heartbeat_state(tmp_path)["result"] == "NORMALIZED"
    assert runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    ) == 0
    after = capsys.readouterr().out
    assert "PASS: HEARTBEAT_LIFECYCLE: status=STOPPED" in after
    assert "DOCTOR: PASS" in after


def test_doctor_passes_for_coherent_live_lock_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    heartbeat = runner.Heartbeat(tmp_path, "active-doctor")
    heartbeat.write(status="RUNNING", force=True)
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    lock = tmp_path / "track-a-runner.lock"
    with lock.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner.doctor_command(
            worktree,
            tmp_path,
            tmp_path / "state.json",
            repository_factory=DoctorRepository,  # type: ignore[arg-type]
            reachable_recovery_validator=_valid_reachable_recovery_inputs,
            network_probe=_passing_network_probe,
        ) == 0
    output = capsys.readouterr().out
    assert f"PASS: RUNNER_LOCK: status=HELD; owner_pids=[{os.getpid()}]" in output
    assert "PASS: HEARTBEAT_LIFECYCLE: status=RUNNING" in output
    assert "DOCTOR: PASS" in output


def test_doctor_fails_named_incoherent_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    heartbeat = runner.Heartbeat(tmp_path, "stopped-doctor")
    heartbeat.stopped("fixture")
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    lock = tmp_path / "track-a-runner.lock"
    with lock.open("a+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner.doctor_command(
            worktree,
            tmp_path,
            tmp_path / "state.json",
            repository_factory=DoctorRepository,  # type: ignore[arg-type]
            reachable_recovery_validator=_valid_reachable_recovery_inputs,
            network_probe=_passing_network_probe,
        ) == 1
    output = capsys.readouterr().out
    assert "FAIL: RUNNER_LOCK: exception=RunnerError: flock is held without a RUNNING heartbeat" in output
    assert "FAIL: HEARTBEAT_LIFECYCLE: exception=RunnerError: STOPPED heartbeat is incoherent with a held flock" in output
    assert "FAILED_CHECK_COUNT: 2" in output
    assert "DOCTOR: FAIL" in output


class EventCollector:
    def __init__(self, root: Path) -> None:
        self.events: list[tuple[runner.EventType, dict]] = []
        self.run_dir = root / "logs"
        self.run_dir.mkdir()

    def emit_event(self, event: runner.EventType, **fields: object) -> None:
        self.events.append((event, dict(fields)))


class MachineHeartbeat:
    review_attempt = 1
    network_retry_count = 0
    network_retry_role: str | None = None
    network_retry_position: int | None = None

    def update_snapshot(self, snapshot: legacy.Snapshot) -> None:
        pass

    def set_review_attempt(
        self,
        attempt: int,
        network_retry_count: int,
        **fields: object,
    ) -> None:
        self.review_attempt = attempt
        self.network_retry_count = network_retry_count
        if isinstance(fields.get("role"), str):
            self.network_retry_role = fields["role"]  # type: ignore[assignment]
        if isinstance(fields.get("position"), int):
            self.network_retry_position = fields["position"]  # type: ignore[assignment]


class MachineRepository:
    def __init__(self, root: Path, terminal: str) -> None:
        self.run_path = root / "run"
        self.run_path.mkdir()
        self.ledger_path = self.run_path / "ledger.json"
        self.ledger_path.write_text("{}\n", encoding="utf-8")
        self.published = False
        self.terminal = terminal
        self.head = "a" * 40
        self.state = {"expected_head": self.head}

    def snapshot(self) -> legacy.Snapshot:
        return _snapshot(
            position=23 if self.published else 22,
            records=22 if self.published else 21,
            head=self.head,
        )

    def durable_token(self, position: int) -> legacy.DurableToken:
        return legacy.DurableToken(self.head, "p", "l", "t")

    def actual_head(self) -> str:
        return self.head

    def accept_controller_head(self, execution: object, before: object) -> None:
        self.state["expected_head"] = self.head

    def last_terminal_processing_state(self, position: int) -> str:
        return self.terminal

    def position_path(self, position: int) -> Path:
        return self.run_path / "positions" / f"{position:08d}"


class MachineExecutor:
    def __init__(self, repository: MachineRepository) -> None:
        self.repository = repository
        self.calls = 0

    def execute(
        self, role: legacy.Role, position: int, expected_head: str
    ) -> legacy.RoleExecution:
        self.calls += 1
        self.repository.published = True
        self.repository.head = "b" * 40
        return legacy.RoleExecution(
            role=role,
            position=position,
            invocation_id=f"fresh-{self.calls}",
            started_at_utc=runner.utc_now(),
            ended_at_utc=runner.utc_now(),
            exit_code=0,
            stdout="AUTO_CONTINUE prose must be ignored",
            stderr="",
            prompt="fixture",
            prompt_sha256="c" * 64,
        )


class SequenceClassifier:
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
        self.calls += 1
        if snapshot.records_published == 21:
            return runner.Classification(
                runner.DurableState.AUTO_MECHANICAL_TERMINAL,
                "fixture",
                legacy.Role.POSITION_CONTROLLER,
            )
        return runner.Classification(
            runner.DurableState.PRE_POSITION,
            "next unopened",
            None,
            "CURRENT_POSITION_MATERIALIZATION",
        )


def test_canonical_decision_processing_error_is_engineering_blocker_without_retry(
    tmp_path: Path,
) -> None:
    class NeverExecutor:
        calls = 0

        def execute(self, *args: object, **kwargs: object) -> legacy.RoleExecution:
            self.calls += 1
            raise AssertionError("reviewer/controller must not launch")

    class FailingClassifier:
        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            raise legacy.CanonicalDecisionProcessingError("synthetic canonical failure")

    repository = MachineRepository(tmp_path, "REVIEW_REJECT")
    logger = EventCollector(tmp_path)
    executor = NeverExecutor()
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = FailingClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.BLOCKER
    assert executor.calls == 0
    blocker = [fields for event, fields in logger.events if event is runner.EventType.BLOCKER]
    assert blocker[-1]["blocker_category"] == "ENGINEERING_BLOCKER"
    assert blocker[-1]["blocker_code"] == "CANONICAL_DECISION_PROCESSING_FAILED"
    assert not runner.canonical_decision_processing_allows_retry()


@pytest.mark.parametrize(
    ("scenario_id", "terminal"),
    [("T25", "ADMIT_FINAL"), ("T26", "REVIEW_REJECT")],
)
def test_autocontinue_requires_validated_terminal_publication(
    tmp_path: Path, scenario_id: str, terminal: str
) -> None:
    repository = MachineRepository(tmp_path, terminal)
    logger = EventCollector(tmp_path)
    executor = MachineExecutor(repository)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = SequenceClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.MAX_POSITION_STOP
    event_types = [event for event, _fields in logger.events]
    assert event_types.index(runner.EventType.ROLE_COMPLETED) < event_types.index(
        runner.EventType.AUTO_CONTINUE
    )
    auto = next(fields for event, fields in logger.events if event is runner.EventType.AUTO_CONTINUE)
    assert auto["records_published"] == 22
    assert auto["next_due_position"] == 23


def test_no_role_exit_autocontinue_event(tmp_path: Path) -> None:
    repository = MachineRepository(tmp_path, "REVIEW_REJECT")
    logger = EventCollector(tmp_path)
    executor = MachineExecutor(repository)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = SequenceClassifier()  # type: ignore[assignment]
    machine.run(1)
    role_event = next(fields for event, fields in logger.events if event is runner.EventType.ROLE_COMPLETED)
    assert role_event["reason"] == "role process exited; durable reconciliation follows"
    expected_stdout = b"AUTO_CONTINUE prose must be ignored"
    assert role_event["stdout_sha256"] == runner.sha256_bytes(expected_stdout)
    assert role_event["stderr_sha256"] == runner.sha256_bytes(b"")
    assert role_event["stdout_bytes"] == len(expected_stdout)
    assert role_event["stderr_bytes"] == 0
    assert "AUTO_CONTINUE" not in role_event


def test_max_positions_semantics(tmp_path: Path) -> None:
    repository = MachineRepository(tmp_path, "REVIEW_REJECT")
    logger = EventCollector(tmp_path)
    executor = MachineExecutor(repository)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = SequenceClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.positions_completed == 1
    assert executor.calls == 1
    assert outcome.next_due_position == 23


def test_fresh_process_and_no_resume(tmp_path: Path) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "fresh")
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.heartbeat = heartbeat
    executor.model = "fixture"
    executor.profile = None
    pids = []
    for index in range(2):
        role_dir = tmp_path / f"role-{index}"
        role_dir.mkdir()
        execution = executor._run_process(
            ["bash", "-c", "printf '%s' $$"],
            cwd=tmp_path,
            role=legacy.Role.POSITION_CONTROLLER,
            position=22,
            prompt="",
            prompt_digest="a" * 64,
            invocation_id=f"fresh-{index}",
            started=runner.utc_now(),
            role_dir=role_dir,
            last_message_path=None,
        )
        pids.append(int(execution.stdout))
    assert pids[0] != pids[1]
    assert "resume" not in legacy.CodexRoleExecutor._base_codex_arguments(executor)
    assert "--ephemeral" in legacy.CodexRoleExecutor._base_codex_arguments(executor)


def test_classifier_never_opens_candidate_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FakeRepository(tmp_path)
    _materialized(repository)
    opened: list[str] = []
    original = runner.read_json

    def guarded(path: Path) -> object:
        opened.append(path.name)
        if path.name == "candidate-manifest.json":
            raise AssertionError("substantive candidate manifest was opened")
        return original(path)

    monkeypatch.setattr(runner, "read_json", guarded)
    result = runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]
    assert result.state is runner.DurableState.POSITION_MATERIALIZED
    assert "candidate-manifest.json" not in opened


def test_combined_review_is_exact_projection_of_both_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = object.__new__(runner.ProductionRepositoryV2)
    repository.worktree = tmp_path
    repository.run_path = tmp_path / runner.RUN_RELATIVE_PATH
    position = repository.position_path(22)
    position.mkdir(parents=True)
    answers = [
        {
            "question_id": f"Q{index}",
            "answer": "UNKNOWN",
            "evidence_refs": [],
            "reason": "fixture",
        }
        for index in range(1, 11)
    ]
    semantic = {
        "candidate_id": "candidate",
        "review_packet_sha256": "a" * 64,
        "answers": answers,
        "outcome": "REVIEW_RETAIN",
        "focal_hypothesis": {"hypothesis_id": "focal"},
    }
    decisions = {
        legacy.Role.AI_FIRST_REVIEW: {
            "decision_sha256": "b" * 64,
            "semantic_decision": semantic,
        },
        legacy.Role.AI_SECOND_REVIEW: {
            "decision_sha256": "c" * 64,
            "semantic_decision": semantic,
        },
    }
    monkeypatch.setattr(
        repository,
        "validate_ai_decision",
        lambda path, role: decisions[role],
    )
    combined = {
        "schema": "candidate-screening-combined-review-v0.2.0",
        "protocol_id": "candidate-screening-v0.2.0",
        "screening_method_version": "tptm-hybrid-screening-v1",
        "queue_position": 22,
        "candidate_id": "candidate",
        "review_packet_sha256": "a" * 64,
        "reviewer_a_decision_sha256": "b" * 64,
        "reviewer_b_decision_sha256": "c" * 64,
        "reviewer_a_outcome": "REVIEW_RETAIN",
        "reviewer_b_outcome": "REVIEW_RETAIN",
        "semantic_decision_disagreement": False,
        "question_disagreements": {f"Q{index}": False for index in range(1, 11)},
        "focal_hypothesis_disagreement": False,
        "reviewer_a_focal_hypothesis": {"hypothesis_id": "focal"},
        "reviewer_b_focal_hypothesis": {"hypothesis_id": "focal"},
        "combined_outcome": "REVIEW_RETAIN",
        "authorized_next_action": "AGREEMENT",
        "combined_review_sha256": "d" * 64,
    }
    path = position / "combined-review.json"
    _write(path, combined)
    assert repository.validate_combined_review(22, path) == combined
    combined["question_disagreements"]["Q1"] = True
    _write(path, combined)
    with pytest.raises(runner.RunnerError, match="exact combination"):
        repository.validate_combined_review(22, path)


def test_executable_validation_is_final_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = object.__new__(runner.ProductionRepositoryV2)
    repository.worktree = tmp_path
    repository.run_path = tmp_path / runner.RUN_RELATIVE_PATH
    position = repository.position_path(22)
    position.mkdir(parents=True)
    family = {
        "candidate_id": "candidate",
        "family_feasibility_sha256": "a" * 64,
        "family_recipe_sha256": "b" * 64,
    }
    family_path = position / "family-feasibility.json"
    _write(family_path, family)
    evidence = position / "executable-evidence.json"
    _write(evidence, {"sanitized": True})
    evidence_relative = str(evidence.relative_to(tmp_path))
    payload = {
        "schema": "candidate-screening-family-executable-validation-v0.1",
        "protocol_id": "candidate-screening-v0.2.0",
        "screening_method_version": "tptm-hybrid-screening-v1",
        "queue_position": 22,
        "candidate_id": "candidate",
        "family_feasibility_sha256": "a" * 64,
        "family_feasibility_file_sha256": runner.sha256_file(family_path),
        "family_recipe_sha256": "b" * 64,
        "validation_state": "PASSED",
        "p_star_source": True,
        "p_star_compatible": True,
        "p_star_invalidated": False,
        "functional_oracles_state": "PASS",
        "reuse_witness_state": "TRIGGERED",
        "safe_witness_state": "BLOCKED",
        "focal_trust_change_count": 1,
        "repository_independence_state": "PASS",
        "trust_category": "AUTHENTICITY",
        "evidence_paths": [evidence_relative],
        "evidence_sha256": {evidence_relative: runner.sha256_file(evidence)},
    }
    executable = {
        **payload,
        "executable_validation_sha256": runner.sha256_bytes(
            legacy.canonical_json_bytes(payload)
        ),
    }
    executable_path = position / "family-executable-validation.json"
    _write(executable_path, executable)
    assert repository.validate_executable_metadata(
        22, executable_path, family
    )["validation_state"] == "PASSED"

    invalid_payload = {**payload, "p_star_invalidated": True}
    _write(
        executable_path,
        {
            **invalid_payload,
            "executable_validation_sha256": runner.sha256_bytes(
                legacy.canonical_json_bytes(invalid_payload)
            ),
        },
    )
    with pytest.raises(runner.RunnerError, match="final authority"):
        repository.validate_executable_metadata(22, executable_path, family)

    _write(executable_path, executable)
    monkeypatch.setattr(
        repository,
        "validate_family_metadata",
        lambda position, path, combined: family,
    )
    repository.validate_terminal_evidence(
        22,
        {
            "processing_state": "ADMIT_FINAL",
            "family_executable_validation_state": "PASSED",
            "family_recipe_sha256": "b" * 64,
            "admission_state": "ADMIT_FINAL",
        },
    )
    executable_path.unlink()
    with pytest.raises(legacy.RunnerError, match="required regular JSON"):
        repository.validate_terminal_evidence(
            22,
            {
                "processing_state": "ADMIT_FINAL",
                "family_executable_validation_state": "PASSED",
                "family_recipe_sha256": "b" * 64,
                "admission_state": "ADMIT_FINAL",
            },
        )


def test_global_stop(tmp_path: Path) -> None:
    repository = FakeRepository(tmp_path)
    result = runner.DurableClassifier(repository).classify(
        _snapshot(action="STOP_TARGET_REACHED")
    )  # type: ignore[arg-type]
    assert result.state is runner.DurableState.GLOBAL_STOP
    assert result.next_role is None


def test_controller_crash_reconciles_durable_state(tmp_path: Path) -> None:
    class CrashAfterCommitExecutor(MachineExecutor):
        def execute(
            self, role: legacy.Role, position: int, expected_head: str
        ) -> legacy.RoleExecution:
            return replace(
                super().execute(role, position, expected_head),
                exit_code=-15,
            )

    repository = MachineRepository(tmp_path, "REVIEW_REJECT")
    logger = EventCollector(tmp_path)
    executor = CrashAfterCommitExecutor(repository)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = SequenceClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.MAX_POSITION_STOP
    assert executor.calls == 1
    assert any(event is runner.EventType.AUTO_CONTINUE for event, _ in logger.events)


@pytest.mark.parametrize(
    "role", [legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW]
)
def test_ai_reviewer_crash_without_decision_retries_fresh(
    tmp_path: Path, role: legacy.Role
) -> None:
    class ReviewRepository:
        def __init__(self, root: Path) -> None:
            self.run_path = root / "run"
            self.run_path.mkdir()
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")
            self.state = {"expected_head": "a" * 40}
            self.head = "a" * 40
            self.reviewed = False

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot(
                head=self.head,
                action="STOP_AFTER_REVIEW" if self.reviewed else "CONTINUE",
            )

        def _snapshot_at_actual_head(self) -> legacy.Snapshot:
            return self.snapshot()

        def durable_token(self, position: int) -> legacy.DurableToken:
            return legacy.DurableToken(self.head, "p", "l", "t")

        def actual_head(self) -> str:
            return self.head

        def accept_reviewer(
            self, execution: legacy.RoleExecution, before: legacy.DurableToken
        ) -> None:
            assert before.head == self.head
            self.reviewed = True
            self.head = "b" * 40
            self.state["expected_head"] = self.head

        def position_path(self, position: int) -> Path:
            return self.run_path / "positions" / f"{position:08d}"

    class ReviewExecutor:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def execute(
            self, actual_role: legacy.Role, position: int, expected_head: str
        ) -> legacy.RoleExecution:
            assert actual_role is role
            invocation = f"fresh-{len(self.calls) + 1}"
            self.calls.append(invocation)
            return legacy.RoleExecution(
                role=actual_role,
                position=position,
                invocation_id=invocation,
                started_at_utc=runner.utc_now(),
                ended_at_utc=runner.utc_now(),
                exit_code=-15 if len(self.calls) == 1 else 0,
                stdout="",
                stderr="",
                prompt="fixture",
                prompt_sha256="c" * 64,
            )

    class ReviewClassifier:
        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            if snapshot.global_action != "CONTINUE":
                return runner.Classification(
                    runner.DurableState.GLOBAL_STOP, "fixture stop", None
                )
            state = (
                runner.DurableState.AI_FIRST_REVIEW_REQUIRED
                if role is legacy.Role.AI_FIRST_REVIEW
                else runner.DurableState.AI_SECOND_REVIEW_REQUIRED
            )
            return runner.Classification(state, "fixture review", role)

    repository = ReviewRepository(tmp_path)
    executor = ReviewExecutor()
    logger = EventCollector(tmp_path)
    machine = runner.DurableStateMachine(
        repository, executor, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    machine.classifier = ReviewClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.GLOBAL_STOP
    assert executor.calls == ["fresh-1", "fresh-2"]
    assert len(set(executor.calls)) == 2


def test_sanitized_position_22_recovery_reaches_tptm_without_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MaterializationRepository(FakeRepository):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")
            self.commits: list[list[Path]] = []

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot()

        def _snapshot_at_actual_head(self) -> legacy.Snapshot:
            return _snapshot()

        def _commit_paths(
            self, message: str, paths: list[Path], position: int
        ) -> None:
            assert position == 22
            self.commits.append(list(paths))

    repository = MaterializationRepository(tmp_path)
    blocker_source = runner.DEFAULT_WORKTREE / runner.RUN_RELATIVE_PATH / (
        "positions/00000022/autonomous-blocker.json"
    )
    blocker = repository.position_path(22) / "autonomous-blocker.json"
    blocker.parent.mkdir(parents=True)
    shutil.copyfile(blocker_source, blocker)
    blocker_before = blocker.read_bytes()
    classification = runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]
    assert classification.state is runner.DurableState.POSITION_MATERIALIZATION_REQUIRED

    def materialize(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        root = repository.position_path(22)
        _write(
            root / "position-authorization.json",
            {
                "schema": "candidate-screening-position-authorization-v0.2.0",
                "queue_position": 22,
                "position_23_authorized": False,
            },
        )
        (root / "candidate-manifest.json").write_text(
            "SEALED FIXTURE BYTES\n", encoding="utf-8"
        )
        _write(root / "position-materialization-recovery.json", {"queue_position": 22})
        return subprocess.CompletedProcess(command, 0, stdout="{}\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", materialize)
    monkeypatch.setattr(
        runner,
        "run_current_materialization_preflight",
        lambda repository, position: {"pass": True, "writes_performed": False},
    )
    logger = EventCollector(tmp_path)
    recovery = runner.RecoveryEngine(
        repository, logger, MachineHeartbeat()  # type: ignore[arg-type]
    )
    recovery.run(classification, 22)
    after = runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]
    assert after.state is runner.DurableState.TPTM_REQUIRED
    assert blocker.read_bytes() == blocker_before
    assert len(repository.commits) == 1
    assert not repository.position_path(23).exists()


def test_status_suppresses_nonexistent_child(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "missing-child")
    heartbeat.update_snapshot(_snapshot())
    heartbeat.set_role("POSITION_CONTROLLER", 2_000_000_000)
    assert runner.status_command(tmp_path) == 0
    output = capsys.readouterr().out
    assert "STATUS: RUNNING" in output
    assert "CHILD_PID: -" in output


def test_discovery_recovery_handler_is_reachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = FakeRepository(tmp_path)
    monkeypatch.setattr(repository, "discovery_materialization_ready", lambda: False)
    classifier = runner.DurableClassifier(repository)  # type: ignore[arg-type]
    monkeypatch.setattr(classifier, "_due_is_administrative", lambda position: False)
    classification = classifier.classify(_snapshot())
    assert classification.state is runner.DurableState.DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED
    assert classification.recovery_id == "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING"
    called: list[int] = []
    engine = runner.RecoveryEngine(
        repository, EventCollector(tmp_path), MachineHeartbeat()  # type: ignore[arg-type]
    )
    monkeypatch.setattr(engine, "_provision_discovery", lambda position: called.append(position))
    engine.run(classification, 22)
    assert called == [22]


def test_materialized_pair_validator_is_delegated(tmp_path: Path) -> None:
    class RejectingRepository(FakeRepository):
        def validate_materialized_position(self, position: int) -> None:
            raise runner.RunnerError("tampered materialized pair")

    repository = RejectingRepository(tmp_path)
    _materialized(repository)
    with pytest.raises(runner.RunnerError, match="tampered materialized pair"):
        runner.DurableClassifier(repository).classify(_snapshot())  # type: ignore[arg-type]


def test_doctor_is_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    monkeypatch.setattr(runner.shutil, "which", lambda name: "/fixture/codex")
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )

    def fingerprint(root: Path) -> dict[str, str]:
        return {
            str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }

    before = fingerprint(tmp_path)
    assert runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=_passing_network_probe,
    ) == 0
    capsys.readouterr()
    assert fingerprint(tmp_path) == before


def test_dry_run_preflight_does_not_invoke_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = object.__new__(runner.ProductionRepositoryV2)
    repository.worktree = tmp_path / "production"
    repository.worktree.mkdir()
    repository.runner_root = tmp_path / "runner"
    repository.state = {"expected_head": "a" * 40}
    snapshot = _snapshot()
    monkeypatch.setattr(repository, "branch", lambda: runner.EXPECTED_BRANCH)
    monkeypatch.setattr(runner, "validate_runtime_interface_coverage", lambda path: {})
    monkeypatch.setattr(repository, "_verify_amendment_chain", lambda: {})
    monkeypatch.setattr(
        repository,
        "_repair_valid_ledger_sidecar_if_needed",
        lambda *, dry_run: None,
    )
    monkeypatch.setattr(repository, "_snapshot_at_actual_head", lambda: snapshot)
    monkeypatch.setattr(repository, "_reconcile_expected_head", lambda value: None)
    monkeypatch.setattr(repository, "_validate_worktree_boundary", lambda position: None)
    monkeypatch.setattr(repository, "snapshot", lambda: snapshot)
    monkeypatch.setattr(
        runner,
        "DurableClassifier",
        lambda repository: SimpleNamespace(
            classify=lambda value: runner.Classification(
                runner.DurableState.POSITION_MATERIALIZATION_REQUIRED,
                "fixture",
                None,
                "CURRENT_POSITION_MATERIALIZATION",
            )
        ),
    )
    monkeypatch.setattr(
        runner,
        "validate_reachable_recovery_inputs",
        lambda repository, classification, position: {
            "pass": True,
            "writes_performed": False,
        },
    )

    def forbidden_codex(*args: object, **kwargs: object) -> dict[str, str]:
        raise AssertionError("dry-run must invoke zero Codex processes")

    monkeypatch.setattr(runner, "verify_codex_cli", forbidden_codex)
    assert repository.preflight(
        dry_run=True, codex_bin=Path("/fixture/codex")
    ) == snapshot


def test_role_process_records_streams_and_exit(tmp_path: Path) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "streams")
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.heartbeat = heartbeat
    executor.model = "fixture"
    executor.profile = None
    role_dir = tmp_path / "role"
    role_dir.mkdir()
    execution = executor._run_process(
        ["bash", "-c", "printf out; printf err >&2; exit 7"],
        cwd=tmp_path,
        role=legacy.Role.POSITION_CONTROLLER,
        position=22,
        prompt="fixture\n",
        prompt_digest="a" * 64,
        invocation_id="streams",
        started=runner.utc_now(),
        role_dir=role_dir,
        last_message_path=None,
    )
    assert execution.exit_code == 7
    assert execution.stdout == "out"
    assert execution.stderr == "err"
    assert (role_dir / "stdout.jsonl").read_text() == "out"
    assert (role_dir / "stderr.txt").read_text() == "err"


def test_role_launch_os_error_reports_canonical_executable_diagnostics(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-codex"
    heartbeat = runner.Heartbeat(tmp_path, "missing-role")
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.heartbeat = heartbeat
    executor.codex_bin = missing
    executor.model = "fixture"
    executor.profile = None
    role_dir = tmp_path / "role-missing"
    role_dir.mkdir()
    with pytest.raises(runner.RunnerError) as raised:
        executor._run_process(
            [str(missing), "exec"],
            cwd=tmp_path,
            role=legacy.Role.POSITION_CONTROLLER,
            position=22,
            prompt="fixture\n",
            prompt_digest="a" * 64,
            invocation_id="missing-role",
            started=runner.utc_now(),
            role_dir=role_dir,
            last_message_path=None,
        )
    message = str(raised.value)
    assert f"attempted_executable_path={missing}" in message
    assert "exists=false" in message
    assert "executable=false" in message
    assert "version_check_status=PASS_AT_PRE_RUN_PREFLIGHT" in message
    assert "exact_os_error=FileNotFoundError:" in message


def test_terminal_global_stop_has_no_auto_continue(tmp_path: Path) -> None:
    class StopRepository(FakeRepository):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot(action="STOP_TARGET_REACHED")

    class ForbiddenExecutor:
        def execute(self, *args: object, **kwargs: object) -> legacy.RoleExecution:
            raise AssertionError("global stop must not invoke a role")

    repository = StopRepository(tmp_path)
    logger = EventCollector(tmp_path)
    machine = runner.DurableStateMachine(
        repository,
        ForbiddenExecutor(),  # type: ignore[arg-type]
        logger,
        MachineHeartbeat(),  # type: ignore[arg-type]
    )
    outcome = machine.run(1)
    assert outcome.event is runner.EventType.GLOBAL_STOP
    assert runner.EventType.AUTO_CONTINUE not in {event for event, _ in logger.events}


@pytest.mark.parametrize(
    ("terminal_event", "expected_exit"),
    [
        (runner.EventType.BLOCKER, 1),
        (runner.EventType.ERROR, 1),
        (runner.EventType.GLOBAL_STOP, 0),
        (runner.EventType.MAX_POSITION_STOP, 0),
    ],
)
def test_main_exit_paths_finalize_stopped_heartbeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal_event: runner.EventType,
    expected_exit: int,
) -> None:
    class MainRepository:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def preflight(
            self, *, dry_run: bool, codex_bin: Path | None
        ) -> legacy.Snapshot:
            assert dry_run is False
            assert codex_bin == Path("/fixture/codex")
            return _snapshot()

    class MainClassifier:
        def __init__(self, repository: object) -> None:
            pass

        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            return runner.Classification(
                runner.DurableState.POSITION_MATERIALIZATION_REQUIRED,
                "fixture",
                None,
                "CURRENT_POSITION_MATERIALIZATION",
            )

    class MainExecutor:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

    class MainMachine:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def run(self, max_positions: int) -> runner.RunnerOutcome:
            assert max_positions == 1
            reason = f"fixture {terminal_event.value.lower()}"
            if terminal_event is runner.EventType.ERROR:
                raise runner.RunnerError(reason)
            return runner.RunnerOutcome(terminal_event, 0, 22, reason)

    monkeypatch.setattr(runner, "ProductionRepositoryV2", MainRepository)
    monkeypatch.setattr(runner, "DurableClassifier", MainClassifier)
    monkeypatch.setattr(runner, "CodexRoleExecutorV2", MainExecutor)
    monkeypatch.setattr(runner, "DurableStateMachine", MainMachine)
    monkeypatch.setattr(
        runner,
        "resolve_canonical_codex_executable",
        lambda requested=None: Path("/fixture/codex"),
    )

    worktree = tmp_path / "production"
    worktree.mkdir()
    result = runner.main(
        [
            "--runner-root",
            str(tmp_path),
            "--worktree",
            str(worktree),
            "--state-file",
            str(tmp_path / "state/runner-state.json"),
            "--codex-bin",
            "/fixture/codex",
            "--max-positions",
            "1",
        ]
    )
    assert result == expected_exit
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["schema"] == runner.HEARTBEAT_SCHEMA
    assert value["status"] == "STOPPED"
    assert value["runner_pid"] is None
    assert value["child_pid"] is None
    assert value["last_runner_pid"] == os.getpid()
    assert value["last_reason"] == f"fixture {terminal_event.value.lower()}"


def test_main_emits_structured_pre_run_blocker_without_production_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    sentinel = production / "sentinel"
    sentinel.write_bytes(b"unchanged")

    class BlockedRepository:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def preflight(self, *, dry_run: bool, codex_bin: Path | None) -> legacy.Snapshot:
            raise runner.RunnerError(
                "CURRENT_POSITION_MATERIALIZATION_INPUTS: "
                "error_code=ARTIFACT_HASH_MISMATCH"
            )

    monkeypatch.setattr(runner, "ProductionRepositoryV2", BlockedRepository)
    monkeypatch.setattr(
        runner,
        "resolve_canonical_codex_executable",
        lambda requested=None: Path("/fixture/codex"),
    )
    assert runner.main(
        [
            "--runner-root",
            str(tmp_path / "runner"),
            "--worktree",
            str(production),
            "--max-positions",
            "3",
        ]
    ) == 1
    events = list((tmp_path / "runner/logs").glob("*/events.jsonl"))
    assert len(events) == 1
    rows = [json.loads(line) for line in events[0].read_text().splitlines()]
    assert rows[-1]["event_type"] == runner.EventType.PRE_RUN_BLOCKER.value
    assert "ARTIFACT_HASH_MISMATCH" in rows[-1]["reason"]
    assert sentinel.read_bytes() == b"unchanged"


def test_transition_coverage_manifest_is_exact() -> None:
    coverage = runner.validate_coverage_manifest()
    rows = coverage["required_scenarios"]
    assert coverage["schema"] == "track-a-transition-test-coverage-v0.1"
    assert len(rows) == 67
    assert [row["id"] for row in rows] == [f"T{index:02d}" for index in range(1, 68)]
    assert all(row["test"] and row["scenario"] for row in rows)
    assert {row["state"] for row in coverage["state_coverage"]} == {
        state.value for state in runner.DurableState
    }


def test_all_matrix_states_have_handlers_or_registered_recovery() -> None:
    matrix, registry = runner.validate_transition_definitions()
    assert matrix["codex_prose_authoritative"] is False
    assert "never authorizes an AUTO_CONTINUE event" in matrix[
        "automatic_continuation_semantics"
    ]
    assert matrix["auto_continue_event_rule"].startswith(
        "AUTO_CONTINUE is permitted only after TERMINAL_PUBLISHED"
    )
    recovery_ids = {item["id"] for item in registry["recoveries"]}
    for row in matrix["states"]:
        state = runner.DurableState(row["state"])
        if row["deterministic_recovery"] not in {None, "REGISTRY_SELECTED"}:
            assert row["deterministic_recovery"] in recovery_ids
        assert state in runner.STATE_ROLE_HANDLERS


@pytest.mark.parametrize("state", list(runner.DurableState), ids=lambda state: state.value)
def test_every_durable_state_has_transition_row_and_handler(
    state: runner.DurableState,
) -> None:
    matrix, registry = runner.validate_transition_definitions()
    row = next(item for item in matrix["states"] if item["state"] == state.value)
    recovery_ids = {item["id"] for item in registry["recoveries"]}
    handler = runner.STATE_ROLE_HANDLERS[state]
    recovery = row["deterministic_recovery"]
    assert row["recognition"]
    assert row["required_files"]
    assert row["forbidden_conflicts"]
    assert row["ledger_relationship"]
    assert row["head_behavior"]
    assert row["fail_closed"]
    assert handler is not None or recovery in recovery_ids or state in {
        runner.DurableState.TERMINAL_PUBLISHED,
        runner.DurableState.GLOBAL_STOP,
    }


def test_position_23_is_terminal_and_positions_24_25_remain_unopened() -> None:
    run = runner.DEFAULT_WORKTREE / runner.RUN_RELATIVE_PATH
    assert (run / "positions/00000023").is_dir()
    assert (run / "records/00000023.json").is_file()
    assert not (run / "positions/00000024").exists()
    assert not (run / "records/00000024.json").exists()
    assert not (run / "positions/00000025").exists()
    assert not (run / "records/00000025.json").exists()


def _failed_network_probe(
    role: str = "AI_FIRST_REVIEW",
) -> runner.review_network.SandboxNetworkProbe:
    return runner.review_network.SandboxNetworkProbe(
        passed=False,
        role=role,
        resolver_mode="SAFE_RUN_TARGET_BIND",
        resolver_target="/run/systemd/resolve/stub-resolv.conf",
        dns_status="FAIL",
        https_status="NOT_REACHED",
        retryable=True,
        reason="fixture network unavailable",
    )


def _resolver_fixture(
    tmp_path: Path, target: str, *, create_target: bool = True
) -> Path:
    root = tmp_path / "host"
    (root / "etc").mkdir(parents=True)
    logical_target = Path(target.lstrip("/"))
    target_path = root / logical_target
    if create_target:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("nameserver 127.0.0.53\n", encoding="ascii")
    (root / "etc/resolv.conf").symlink_to(target)
    return root


def test_fedora_resolver_symlink_gets_exact_target_bind(tmp_path: Path) -> None:
    target = "/run/systemd/resolve/stub-resolv.conf"
    root = _resolver_fixture(tmp_path, target)
    policy = runner.review_network.resolve_resolver_mount_policy(host_root=root)
    assert policy.mode == "SAFE_RUN_TARGET_BIND"
    assert str(policy.namespace_target) == target
    assert policy.bwrap_arguments == (
        "--dir",
        "/run",
        "--dir",
        "/run/systemd",
        "--dir",
        "/run/systemd/resolve",
        "--ro-bind",
        str(root / target.lstrip("/")),
        target,
    )


def test_regular_resolv_conf_needs_no_extra_mount(tmp_path: Path) -> None:
    root = tmp_path / "host"
    (root / "etc").mkdir(parents=True)
    (root / "etc/resolv.conf").write_text("nameserver 192.0.2.1\n", encoding="ascii")
    policy = runner.review_network.resolve_resolver_mount_policy(host_root=root)
    assert policy.mode == "REGULAR_FILE_IN_ETC_BIND"
    assert policy.bwrap_arguments == ()


def test_missing_and_unexpected_resolver_targets_fail_closed(tmp_path: Path) -> None:
    missing = _resolver_fixture(
        tmp_path / "missing",
        "/run/systemd/resolve/stub-resolv.conf",
        create_target=False,
    )
    with pytest.raises(
        runner.review_network.ReviewSandboxConfigurationError,
        match="target is unavailable",
    ):
        runner.review_network.resolve_resolver_mount_policy(host_root=missing)
    unexpected = _resolver_fixture(tmp_path / "unexpected", "/tmp/resolv.conf")
    with pytest.raises(
        runner.review_network.ReviewSandboxConfigurationError,
        match="unexpected resolver symlink target rejected",
    ):
        runner.review_network.resolve_resolver_mount_policy(host_root=unexpected)


def test_resolver_policy_never_broadly_binds_run(tmp_path: Path) -> None:
    root = _resolver_fixture(
        tmp_path, "/run/systemd/resolve/stub-resolv.conf"
    )
    arguments = runner.review_network.resolve_resolver_mount_policy(
        host_root=root
    ).bwrap_arguments
    bind_sources = {
        arguments[index + 1]
        for index, value in enumerate(arguments[:-2])
        if value == "--ro-bind"
    }
    assert "/run" not in bind_sources
    assert bind_sources == {str(root / "run/systemd/resolve/stub-resolv.conf")}


def test_live_host_dns_works_while_old_exact_sandbox_dns_is_broken() -> None:
    policy = runner.review_network.resolve_resolver_mount_policy()
    if str(policy.namespace_target) != "/run/systemd/resolve/stub-resolv.conf":
        pytest.skip("live host is not using the Fedora systemd-resolved stub target")
    assert subprocess.run(
        ["getent", "ahosts", "chatgpt.com"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0
    result = runner.review_network.probe_reviewer_sandbox_network(
        runner_root=runner.RUNNER_ROOT,
        role=legacy.Role.AI_FIRST_REVIEW.value,
        environment=legacy.sanitized_environment(),
        mount_resolver_target=False,
    )
    assert result.passed is False
    assert result.dns_status == "FAIL"


@pytest.mark.parametrize(
    "role", [legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW]
)
def test_live_corrected_reviewer_sandbox_network_probe(role: legacy.Role) -> None:
    result = runner.review_network.probe_reviewer_sandbox_network(
        runner_root=runner.RUNNER_ROOT,
        role=role.value,
        environment=legacy.sanitized_environment(),
    )
    assert result.passed is True
    assert result.dns_status == "PASS"
    assert result.https_status not in {"000", "NOT_REACHED"}


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def test_five_minute_network_outage_waits_then_allows_fresh_launch(
    tmp_path: Path,
) -> None:
    clock = _FakeClock()
    heartbeat = runner.Heartbeat(tmp_path, "five-minute-wait")
    logger = runner.StructuredLogger(tmp_path, "five-minute-wait", heartbeat)
    launched: list[str] = []

    def probe() -> runner.review_network.SandboxNetworkProbe:
        if clock.value < 300:
            return _failed_network_probe()
        return _passing_network_probe(legacy.Role.AI_FIRST_REVIEW)

    result = runner.wait_for_reviewer_network(
        role=legacy.Role.AI_FIRST_REVIEW,
        position=22,
        probe=probe,
        heartbeat=heartbeat,
        logger=logger,
        clock=clock,
        sleeper=clock.sleep,
        utc_source=lambda: "2026-08-29T05:00:00Z",
    )
    launched.append("fresh-reviewer-process")
    assert result.passed is True
    assert clock.value == 300
    assert launched == ["fresh-reviewer-process"]
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["network_state"] == "CONNECTED"
    assert value["network_wait_seconds"] == 300


def test_persistent_network_outage_has_bounded_blocker(tmp_path: Path) -> None:
    clock = _FakeClock()
    heartbeat = runner.Heartbeat(tmp_path, "persistent-wait")
    logger = runner.StructuredLogger(tmp_path, "persistent-wait", heartbeat)
    with pytest.raises(
        runner.ReviewSandboxNetworkUnavailable,
        match="bounded wait exhausted",
    ):
        runner.wait_for_reviewer_network(
            role=legacy.Role.AI_FIRST_REVIEW,
            position=22,
            probe=_failed_network_probe,
            heartbeat=heartbeat,
            logger=logger,
            clock=clock,
            sleeper=clock.sleep,
            utc_source=lambda: "2026-08-29T05:00:00Z",
        )
    assert clock.value == runner.NETWORK_WAIT_LIMIT_SECONDS
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["network_state"] == "UNAVAILABLE"
    assert value["network_wait_seconds"] == runner.NETWORK_WAIT_LIMIT_SECONDS


def test_reconnect_only_detector_requires_sustained_no_progress() -> None:
    detector = runner.NetworkStallDetector(0.0, 600.0)
    detector.observe("Reconnecting... waiting for network\n", 1.0)
    assert detector.stalled(600.0) is False
    assert detector.stalled(601.0) is True
    detector.observe("tool call completed\n", 602.0)
    assert detector.stalled(2000.0) is False


class _StallRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def position_path(self, position: int) -> Path:
        return self.root / "positions" / f"{position:08d}"


def _stall_executor(tmp_path: Path, name: str) -> runner.CodexRoleExecutorV2:
    heartbeat = runner.Heartbeat(tmp_path, name)
    logger = runner.StructuredLogger(tmp_path, name, heartbeat)
    executor = object.__new__(runner.CodexRoleExecutorV2)
    executor.heartbeat = heartbeat
    executor.logger = logger
    executor.repository = _StallRepository(tmp_path)
    executor.codex_bin = Path("/bin/bash")
    executor.model = "fixture"
    executor.profile = None
    executor.network_stall_seconds = 0.15
    executor.process_poll_interval_seconds = 0.02
    return executor


def test_running_reconnect_only_reviewer_is_terminated(tmp_path: Path) -> None:
    executor = _stall_executor(tmp_path, "stall-kill")
    role_dir = tmp_path / "role"
    role_dir.mkdir()
    execution = executor._run_process(
        [
            "bash",
            "-c",
            "while true; do echo 'Reconnecting... waiting for network' >&2; sleep 0.03; done",
        ],
        cwd=tmp_path,
        role=legacy.Role.AI_FIRST_REVIEW,
        position=22,
        prompt="fixture\n",
        prompt_digest="a" * 64,
        invocation_id="stall",
        started=runner.utc_now(),
        role_dir=role_dir,
        last_message_path=tmp_path / "last-message.json",
    )
    assert execution.exit_code < 0
    assert execution.infrastructure_failure == "CODEX_NETWORK_STALL"
    assert execution.partial_decision_present is False


def test_long_reviewer_with_semantic_progress_is_not_killed(tmp_path: Path) -> None:
    executor = _stall_executor(tmp_path, "semantic-progress")
    role_dir = tmp_path / "role"
    role_dir.mkdir()
    execution = executor._run_process(
        [
            "bash",
            "-c",
            "for n in $(seq 1 20); do echo 'Reconnecting... waiting for network' >&2; echo 'semantic tool progress'; sleep 0.03; done",
        ],
        cwd=tmp_path,
        role=legacy.Role.AI_SECOND_REVIEW,
        position=22,
        prompt="fixture\n",
        prompt_digest="a" * 64,
        invocation_id="progress",
        started=runner.utc_now(),
        role_dir=role_dir,
        last_message_path=tmp_path / "last-message.json",
    )
    assert execution.exit_code == 0
    assert execution.infrastructure_failure is None


@pytest.mark.parametrize(
    ("mode", "expected_calls", "expected_code"),
    [
        ("RECOVER", 3, None),
        ("DECISION", 1, "DECISION_PRESENT_AFTER_NETWORK_STALL"),
        ("PARTIAL", 1, "AMBIGUOUS_PARTIAL_REVIEW_DECISION"),
        ("EXHAUST", 3, "NETWORK_STALL_RETRY_EXHAUSTED"),
    ],
)
@pytest.mark.parametrize(
    "role", [legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW]
)
def test_network_stall_retry_safety_and_bounds(
    tmp_path: Path,
    mode: str,
    expected_calls: int,
    expected_code: str | None,
    role: legacy.Role,
) -> None:
    class ReviewRepository:
        def __init__(self, root: Path) -> None:
            self.run_path = root / "run"
            self.run_path.mkdir()
            self.ledger_path = self.run_path / "ledger.json"
            self.ledger_path.write_text("{}\n", encoding="utf-8")
            self.state = {"expected_head": "a" * 40}
            self.head = "a" * 40
            self.reviewed = False

        def snapshot(self) -> legacy.Snapshot:
            return _snapshot(
                head=self.head,
                action="STOP_AFTER_REVIEW" if self.reviewed else "CONTINUE",
            )

        def _snapshot_at_actual_head(self) -> legacy.Snapshot:
            return self.snapshot()

        def durable_token(self, position: int) -> legacy.DurableToken:
            return legacy.DurableToken(self.head, "p", "l", "t")

        def actual_head(self) -> str:
            return self.head

        def position_path(self, position: int) -> Path:
            path = self.run_path / "positions" / f"{position:08d}"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def accept_reviewer(
            self, execution: legacy.RoleExecution, before: legacy.DurableToken
        ) -> None:
            self.reviewed = True
            self.head = "b" * 40
            self.state["expected_head"] = self.head

    class ReviewExecutor:
        def __init__(self, repository: ReviewRepository) -> None:
            self.repository = repository
            self.calls: list[str] = []

        def execute(
            self, actual_role: legacy.Role, position: int, expected_head: str
        ) -> legacy.RoleExecution:
            invocation = f"fresh-{len(self.calls) + 1}"
            self.calls.append(invocation)
            successful = mode == "RECOVER" and len(self.calls) == 3
            if mode == "DECISION" and len(self.calls) == 1:
                decision_name = (
                    "ai-reviewer-a-decision.json"
                    if role is legacy.Role.AI_FIRST_REVIEW
                    else "ai-reviewer-b-decision.json"
                )
                _write(self.repository.position_path(position) / decision_name, {})
            return legacy.RoleExecution(
                role=actual_role,
                position=position,
                invocation_id=invocation,
                started_at_utc=runner.utc_now(),
                ended_at_utc=runner.utc_now(),
                exit_code=0 if successful else -15,
                stdout="",
                stderr="Reconnecting... waiting for network\n",
                prompt="fixture",
                prompt_sha256="c" * 64,
                infrastructure_failure=(None if successful else "CODEX_NETWORK_STALL"),
                partial_decision_present=mode == "PARTIAL",
            )

    class ReviewClassifier:
        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            if snapshot.global_action != "CONTINUE":
                return runner.Classification(
                    runner.DurableState.GLOBAL_STOP, "fixture stop", None
                )
            state = (
                runner.DurableState.AI_FIRST_REVIEW_REQUIRED
                if role is legacy.Role.AI_FIRST_REVIEW
                else runner.DurableState.AI_SECOND_REVIEW_REQUIRED
            )
            return runner.Classification(state, "fixture review", role)

    repository = ReviewRepository(tmp_path)
    executor = ReviewExecutor(repository)
    logger = EventCollector(tmp_path)
    heartbeat = MachineHeartbeat()
    machine = runner.DurableStateMachine(
        repository, executor, logger, heartbeat  # type: ignore[arg-type]
    )
    machine.classifier = ReviewClassifier()  # type: ignore[assignment]
    outcome = machine.run(1)
    assert len(executor.calls) == expected_calls
    assert len(set(executor.calls)) == expected_calls
    if expected_code is None:
        assert outcome.event is runner.EventType.GLOBAL_STOP
        assert heartbeat.network_retry_count == 2
    else:
        assert outcome.event is runner.EventType.BLOCKER
        blocker = next(fields for event, fields in logger.events if event is runner.EventType.BLOCKER)
        assert blocker["blocker_code"] == expected_code


def test_doctor_detects_broken_reviewer_sandbox_dns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _doctor_fixture(tmp_path, materializer=True)
    monkeypatch.setattr(
        runner,
        "verify_codex_cli",
        lambda codex, worktree: {"version": runner.EXPECTED_CODEX_VERSION},
    )
    assert runner.doctor_command(
        worktree,
        tmp_path,
        tmp_path / "state.json",
        repository_factory=DoctorRepository,  # type: ignore[arg-type]
        reachable_recovery_validator=_valid_reachable_recovery_inputs,
        network_probe=lambda role: _failed_network_probe(role.value),
    ) == 1
    output = capsys.readouterr().out
    assert "FAIL: REVIEW_SANDBOX_NETWORK_PREFLIGHT:" in output
    assert "DOCTOR: FAIL" in output


def test_status_and_heartbeat_expose_network_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    heartbeat = runner.Heartbeat(tmp_path, "network-status")
    heartbeat.update_snapshot(_snapshot())
    heartbeat.set_role("AI_FIRST_REVIEW", None)
    heartbeat.set_review_attempt(2, 1)
    heartbeat.set_network_state(
        "WAITING",
        wait_seconds=180,
        failure_since="2026-08-29T05:00:00Z",
        reason="fixture network wait",
    )
    value = json.loads((tmp_path / "state/heartbeat.json").read_text())
    assert value["review_attempt"] == 2
    assert value["network_retry_count"] == 1
    assert value["network_failure_since"] == "2026-08-29T05:00:00Z"
    runner.status_command(tmp_path)
    output = capsys.readouterr().out
    assert "NETWORK_STATE: WAITING" in output
    assert "NETWORK_WAIT_SECONDS: 180" in output
    assert "REVIEW_ATTEMPT: 2" in output
    assert "NETWORK_RETRY_COUNT: 1" in output


def test_pre_run_broken_reviewer_network_prevents_executor_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class MainRepository:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def preflight(
            self, *, dry_run: bool, codex_bin: Path | None
        ) -> legacy.Snapshot:
            return _snapshot()

    class MainClassifier:
        def __init__(self, repository: object) -> None:
            pass

        def classify(self, snapshot: legacy.Snapshot) -> runner.Classification:
            return runner.Classification(
                runner.DurableState.AI_FIRST_REVIEW_REQUIRED,
                "fixture reviewer boundary",
                legacy.Role.AI_FIRST_REVIEW,
            )

    class ForbiddenExecutor:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("broken pre-run network must not launch reviewer")

    def unavailable(**kwargs: object) -> object:
        raise runner.ReviewSandboxNetworkUnavailable(
            "REVIEW_SANDBOX_NETWORK_UNAVAILABLE: fixture"
        )

    monkeypatch.setattr(runner, "ProductionRepositoryV2", MainRepository)
    monkeypatch.setattr(runner, "DurableClassifier", MainClassifier)
    monkeypatch.setattr(runner, "CodexRoleExecutorV2", ForbiddenExecutor)
    monkeypatch.setattr(runner, "wait_for_reviewer_network", unavailable)
    monkeypatch.setattr(
        runner,
        "resolve_canonical_codex_executable",
        lambda requested=None: Path("/fixture/codex"),
    )
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    root = tmp_path / "runner"
    assert runner.main(
        [
            "--runner-root",
            str(root),
            "--worktree",
            str(worktree),
            "--max-positions",
            "1",
        ]
    ) == 1
    event_path = next((root / "logs").glob("*/events.jsonl"))
    events = [json.loads(line) for line in event_path.read_text().splitlines()]
    assert events[-1]["event_type"] == runner.EventType.PRE_RUN_BLOCKER.value
    assert "REVIEW_SANDBOX_NETWORK_UNAVAILABLE" in events[-1]["reason"]

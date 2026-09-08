from __future__ import annotations

import fcntl
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import uuid

import pytest


RUNNER_ROOT = Path("/home/anjum/track-a-production-runner")
REPOSITORY_ROOT = Path(
    "/home/anjum/Documents/research/correct-memory-study-worktrees/"
    "candidate-screening-v020-hybrid"
)
sys.path.insert(0, str(RUNNER_ROOT))

import track_a_runner as runner  # noqa: E402


class MemoryLogger:
    def __init__(self) -> None:
        self.events: list[tuple[runner.Classification, dict[str, Any]]] = []

    def emit(self, classification: runner.Classification, **fields: Any) -> None:
        self.events.append((classification, fields))


class FakeRepository:
    def __init__(
        self,
        *,
        controller_terminal: str | None = None,
        continuation_terminal: str = "REVIEW_REJECT",
        combination_terminal: str = "FAMILY_CONSTRUCTION_FAILED",
        reviewer_b_required: bool = False,
        global_action: str = "CONTINUE",
        stop_after_terminal: bool = False,
        initial_phase: runner.Phase = runner.Phase.NEED_CONTROLLER,
    ) -> None:
        self.records = 21
        self.position = 22
        self.version = 0
        self.head_counter = 1
        self.head = f"{self.head_counter:040x}"
        self.current_phase = initial_phase
        self.controller_terminal = controller_terminal
        self.continuation_terminal = continuation_terminal
        self.combination_terminal = combination_terminal
        self.reviewer_b_required = reviewer_b_required
        self.global_action = global_action
        self.stop_after_terminal = stop_after_terminal
        self.terminals: dict[int, str] = {}
        self.blocker = "SCIENTIFIC_BLOCKER"
        self.accepted_roles: list[tuple[int, runner.Role]] = []
        self.snapshot_error: str | None = None

    def snapshot(self) -> runner.Snapshot:
        if self.snapshot_error:
            raise runner.RunnerError(self.snapshot_error)
        return runner.Snapshot(
            head=self.head,
            records_published=self.records,
            successor_positions_processed=self.records,
            historical_unique_opened_anchors=2,
            global_unique_opened_anchors=19 + max(0, self.records - 21),
            final=sum(state == "ADMIT_FINAL" for state in self.terminals.values()),
            categories_represented=sum(
                state == "ADMIT_FINAL" for state in self.terminals.values()
            ),
            next_due_position=self.position,
            global_action=self.global_action,
        )

    def phase(self, position: int) -> runner.Phase:
        assert position == self.position
        return self.current_phase

    def durable_token(self, position: int) -> runner.DurableToken:
        return runner.DurableToken(
            self.head,
            f"{self.version:064x}",
            f"{self.records:064x}",
            f"{position + self.version:064x}",
        )

    def accept_execution(
        self, execution: runner.RoleExecution, before: runner.DurableToken
    ) -> None:
        assert execution.position == self.position
        self.accepted_roles.append((self.position, execution.role))
        self.version += 1
        self.head_counter += 1
        self.head = f"{self.head_counter:040x}"
        if execution.role is runner.Role.POSITION_CONTROLLER:
            if self.controller_terminal:
                self._publish(self.controller_terminal)
            else:
                self.current_phase = runner.Phase.NEED_REVIEW_A
        elif execution.role is runner.Role.AI_FIRST_REVIEW:
            self.current_phase = runner.Phase.NEED_CONTINUATION
        elif execution.role is runner.Role.CONTINUATION_CONTROLLER:
            if self.reviewer_b_required:
                self.current_phase = runner.Phase.NEED_REVIEW_B
            else:
                self._publish(self.continuation_terminal)
        elif execution.role is runner.Role.AI_SECOND_REVIEW:
            self.current_phase = runner.Phase.NEED_COMBINATION
        elif execution.role is runner.Role.COMBINATION_CONTINUATION_CONTROLLER:
            self._publish(self.combination_terminal)

    def _publish(self, processing_state: str) -> None:
        old_position = self.position
        self.terminals[old_position] = processing_state
        self.records += 1
        self.position += 1
        self.current_phase = runner.Phase.NEED_CONTROLLER
        if self.stop_after_terminal:
            self.global_action = "STOP_TARGET_REACHED"

    def last_terminal_processing_state(self, position: int) -> str:
        return self.terminals[position]

    def blocker_reason(self, position: int) -> str:
        return self.blocker

    def mutate_durably(self) -> None:
        self.version += 1
        self.head_counter += 1
        self.head = f"{self.head_counter:040x}"


class FakeExecutor:
    def __init__(
        self,
        repository: FakeRepository,
        *,
        fail_first_prewrite: bool = False,
        fail_first_postwrite: bool = False,
    ) -> None:
        self.repository = repository
        self.fail_first_prewrite = fail_first_prewrite
        self.fail_first_postwrite = fail_first_postwrite
        self.invocations: list[tuple[int, runner.Role, str]] = []
        self.attempts = 0

    def execute(
        self, role: runner.Role, position: int, expected_head: str
    ) -> runner.RoleExecution:
        self.attempts += 1
        invocation_id = str(uuid.uuid4())
        self.invocations.append((position, role, invocation_id))
        exit_code = 0
        if self.fail_first_prewrite and self.attempts == 1:
            exit_code = 1
        if self.fail_first_postwrite and self.attempts == 1:
            self.repository.mutate_durably()
            exit_code = 1
        prompt = f"role={role.value};position={position};head={expected_head}\n"
        return runner.RoleExecution(
            role=role,
            position=position,
            invocation_id=invocation_id,
            started_at_utc="2026-08-28T00:00:00Z",
            ended_at_utc="2026-08-28T00:00:01Z",
            exit_code=exit_code,
            stdout="",
            stderr="" if exit_code == 0 else "fake failure",
            prompt=prompt,
            prompt_sha256=runner.sha256_bytes(prompt.encode()),
        )


def run_fake(
    repository: FakeRepository,
    *,
    max_positions: int = 1,
    fail_first_prewrite: bool = False,
    fail_first_postwrite: bool = False,
) -> tuple[runner.RunOutcome, FakeExecutor, MemoryLogger]:
    executor = FakeExecutor(
        repository,
        fail_first_prewrite=fail_first_prewrite,
        fail_first_postwrite=fail_first_postwrite,
    )
    logger = MemoryLogger()
    outcome = runner.StateMachine(repository, executor, logger).run(max_positions)
    return outcome, executor, logger


def test_01_automatic_g0_g1_terminal_advances_to_next_position() -> None:
    repo = FakeRepository(controller_terminal="AUTO_MECHANICAL_REJECT")
    outcome, executor, _ = run_fake(repo)
    assert outcome.classification is runner.Classification.MAX_POSITION_STOP
    assert outcome.next_due_position == 23
    assert [role for _, role, _ in executor.invocations] == [
        runner.Role.POSITION_CONTROLLER
    ]


def test_02_unsupported_g2_terminal_advances_to_next_position() -> None:
    repo = FakeRepository(controller_terminal="OUT_OF_SCOPE_UNSUPPORTED")
    outcome, _, _ = run_fake(repo)
    assert outcome.next_due_position == 23
    assert repo.terminals[22] == "OUT_OF_SCOPE_UNSUPPORTED"


def test_03_administrative_terminal_advances_without_review() -> None:
    repo = FakeRepository(controller_terminal="ADMIN_REPOSITORY_ANCHOR_LIMIT")
    outcome, executor, _ = run_fake(repo)
    assert outcome.positions_completed == 1
    assert all("REVIEW" not in role.value for _, role, _ in executor.invocations)


def test_04_structured_review_launches_fresh_ai_a() -> None:
    repo = FakeRepository()
    _, executor, _ = run_fake(repo)
    roles = [role for _, role, _ in executor.invocations]
    assert roles[:2] == [runner.Role.POSITION_CONTROLLER, runner.Role.AI_FIRST_REVIEW]


def test_05_ai_a_reject_continuation_can_terminally_reject() -> None:
    repo = FakeRepository(continuation_terminal="REVIEW_REJECT")
    outcome, executor, _ = run_fake(repo)
    assert outcome.positions_completed == 1
    assert runner.Role.AI_SECOND_REVIEW not in [r for _, r, _ in executor.invocations]
    assert repo.terminals[22] == "REVIEW_REJECT"


def test_06_ai_a_unresolved_uses_constrained_continuation() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="FAMILY_CONSTRUCTION_FAILED",
    )
    outcome, executor, _ = run_fake(repo)
    assert outcome.positions_completed == 1
    assert runner.Role.COMBINATION_CONTINUATION_CONTROLLER in [
        role for _, role, _ in executor.invocations
    ]


def test_07_ai_a_retain_uses_continuation_not_direct_admission() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="FAMILY_VALIDATION_FAILED",
    )
    _, executor, _ = run_fake(repo)
    roles = [role for _, role, _ in executor.invocations]
    assert roles.index(runner.Role.CONTINUATION_CONTROLLER) < roles.index(
        runner.Role.AI_SECOND_REVIEW
    )


def test_08_reviewer_b_required_launches_another_process() -> None:
    repo = FakeRepository(reviewer_b_required=True)
    _, executor, _ = run_fake(repo)
    assert runner.Role.AI_SECOND_REVIEW in [r for _, r, _ in executor.invocations]


def test_09_reviewer_b_not_required_is_not_launched() -> None:
    repo = FakeRepository(reviewer_b_required=False)
    _, executor, _ = run_fake(repo)
    assert runner.Role.AI_SECOND_REVIEW not in [r for _, r, _ in executor.invocations]


def test_10_reviewer_b_prompt_contains_no_a_semantic_material() -> None:
    prompts = json.loads(
        (
            REPOSITORY_ROOT
            / runner.AMENDMENT_RELATIVE_PATH
            / "role-prompts.json"
        ).read_text()
    )
    prompt = "\n".join(prompts["ai_second_review"])
    for forbidden in (
        "AI Reviewer A vector",
        "AI Reviewer A reasoning",
        "AI Reviewer A outcome",
        "AI Reviewer A focal hypothesis",
        "AI Reviewer A source-condition",
    ):
        assert forbidden not in prompt


def test_11_a_b_disagreement_becomes_review_unresolved() -> None:
    base = {
        "candidate_id": "candidate",
        "review_packet_sha256": "a" * 64,
        "answers": [{"question_id": "Q1", "answer": "YES"}],
        "outcome": "REVIEW_RETAIN",
        "focal_hypothesis": {"hypothesis_id": "one"},
    }
    second = {**base, "answers": [{"question_id": "Q1", "answer": "UNKNOWN"}]}
    assert runner.combine_review_metadata(base, second) == (
        "REVIEW_UNRESOLVED",
        "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION",
    )


def test_12_no_unique_focal_hypothesis_uses_frozen_family_failure() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="FAMILY_CONSTRUCTION_FAILED",
    )
    outcome, _, _ = run_fake(repo)
    assert outcome.positions_completed == 1
    assert repo.terminals[22] == "FAMILY_CONSTRUCTION_FAILED"


def test_13_construction_route_is_reachable_only_after_continuation() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="FAMILY_CONSTRUCTION_FAILED",
    )
    _, executor, _ = run_fake(repo)
    roles = [r for _, r, _ in executor.invocations]
    assert roles[-1] is runner.Role.COMBINATION_CONTINUATION_CONTROLLER


def test_14_executable_validation_route_can_fail_terminally() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="FAMILY_VALIDATION_FAILED",
    )
    outcome, _, _ = run_fake(repo)
    assert outcome.positions_completed == 1
    assert repo.terminals[22] == "FAMILY_VALIDATION_FAILED"


def test_15_final_publication_is_terminal_and_chain_advances() -> None:
    repo = FakeRepository(
        reviewer_b_required=True,
        combination_terminal="ADMIT_FINAL",
    )
    outcome, _, _ = run_fake(repo)
    assert outcome.next_due_position == 23
    assert repo.snapshot().final == 1


def test_16_global_stopping_rule_stops_successfully() -> None:
    repo = FakeRepository(global_action="STOP_TARGET_REACHED")
    outcome, executor, _ = run_fake(repo)
    assert outcome.classification is runner.Classification.GLOBAL_STOP
    assert executor.invocations == []


def test_17_durable_blocker_stops_without_role_launch() -> None:
    repo = FakeRepository(initial_phase=runner.Phase.BLOCKER)
    outcome, executor, _ = run_fake(repo)
    assert outcome.classification is runner.Classification.BLOCKER
    assert executor.invocations == []


def test_18_analysis_error_publication_stops_fail_closed() -> None:
    repo = FakeRepository(controller_terminal="ANALYSIS_ERROR")
    outcome, _, _ = run_fake(repo)
    assert outcome.classification is runner.Classification.BLOCKER
    assert "ANALYSIS_ERROR" in outcome.message


def test_19_codex_prewrite_failure_retries_with_new_process() -> None:
    repo = FakeRepository(controller_terminal="AUTO_MECHANICAL_REJECT")
    outcome, executor, _ = run_fake(repo, fail_first_prewrite=True)
    assert outcome.positions_completed == 1
    assert len(executor.invocations) == 2
    assert executor.invocations[0][2] != executor.invocations[1][2]


def test_20_possible_postwrite_failure_stops_without_retry() -> None:
    repo = FakeRepository(controller_terminal="AUTO_MECHANICAL_REJECT")
    outcome, executor, _ = run_fake(repo, fail_first_postwrite=True)
    assert outcome.classification is runner.Classification.ERROR
    assert len(executor.invocations) == 1
    assert "POSSIBLE_DURABLE_CHANGE" in outcome.message


def test_21_head_mismatch_is_fail_closed() -> None:
    repo = FakeRepository()
    repo.snapshot_error = "unexpected HEAD"
    with pytest.raises(runner.RunnerError, match="unexpected HEAD"):
        run_fake(repo)


def test_22_ledger_mismatch_is_fail_closed() -> None:
    repo = FakeRepository()
    repo.snapshot_error = "ledger checksum mismatch"
    with pytest.raises(runner.RunnerError, match="ledger checksum"):
        run_fake(repo)


def test_23_invalid_reviewer_decision_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "invalid.json"
    output.write_text('{"candidate_id":"x"}')
    packet = tmp_path / "packet.json"
    packet.write_text("{}")
    repo = runner.ProductionRepository.__new__(runner.ProductionRepository)
    repo.worktree = REPOSITORY_ROOT
    with pytest.raises(runner.RunnerError, match="fields are not exact"):
        repo._validate_ai_output(output, packet)


def test_23a_review_answer_uses_repository_canonical_projection_bytes() -> None:
    source_root = str(REPOSITORY_ROOT / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        from cmpilot.tptm.canonical import canonical_json_bytes
        from cmpilot.tptm.review import ReviewAnswer, ReviewAnswerValue

        payload = {
            "answers": (
                ReviewAnswer("Q1", ReviewAnswerValue.UNKNOWN, ()),
            )
        }
        encoded = runner.canonical_review_projection_bytes(payload)
        assert encoded == canonical_json_bytes(payload)
        assert json.loads(encoded) == {
            "answers": [
                {"answer": "UNKNOWN", "evidence_refs": [], "question_id": "Q1"}
            ]
        }
    finally:
        if inserted:
            sys.path.remove(source_root)


def test_23b_unsupported_canonical_object_fails_without_retry() -> None:
    source_root = str(REPOSITORY_ROOT / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        with pytest.raises(
            runner.CanonicalDecisionProcessingError,
            match="canonical AI reviewer decision serialization failed",
        ):
            runner.canonical_review_projection_bytes({"unsupported": object()})
        assert not runner.canonical_decision_processing_allows_retry()
    finally:
        if inserted:
            sys.path.remove(source_root)


def test_24_blinding_violation_in_b_assignment_is_rejected(tmp_path: Path) -> None:
    repo = runner.ProductionRepository.__new__(runner.ProductionRepository)
    repo.worktree = tmp_path
    repo.run_path = tmp_path / runner.RUN_RELATIVE_PATH
    position_dir = repo.run_path / "positions" / "00000022"
    position_dir.mkdir(parents=True)
    packet_rel = str(
        runner.RUN_RELATIVE_PATH / "positions" / "00000022" / "review-packet.json"
    )
    forbidden_rel = str(
        runner.RUN_RELATIVE_PATH
        / "positions"
        / "00000022"
        / "reviewer-a-decision.json"
    )
    for relative in (packet_rel, forbidden_rel):
        path = tmp_path / relative
        path.write_text("bounded")
    hashes = {
        relative: runner.sha256_file(tmp_path / relative)
        for relative in (packet_rel, forbidden_rel)
    }
    assignment = {
        "schema_version": "candidate-screening-ai-review-assignment-v0.1",
        "amendment_id": runner.AMENDMENT_ID,
        "protocol_version": "candidate-screening-v0.2.0",
        "status": "AWAITING_AUTHORITATIVE_AI_REVIEW",
        "created_at_utc": "2026-08-28T00:00:00Z",
        "queue_position": 22,
        "reviewer_type": "AI",
        "reviewer_role": "AI_SECOND_REVIEW",
        "authoritative": True,
        "required_execution_boundary": "FRESH_ONE_SHOT_CODEX_PROCESS",
        "candidate_id": "candidate",
        "review_packet": {
            "path": packet_rel,
            "review_packet_sha256": "a" * 64,
            "file_sha256": hashes[packet_rel],
        },
        "permitted_evidence_paths": sorted([packet_rel, forbidden_rel]),
        "permitted_evidence_sha256": hashes,
        "permitted_interface_paths": [],
        "permitted_interface_sha256": {},
        "decision_output_path": str(
            runner.RUN_RELATIVE_PATH
            / "positions"
            / "00000022"
            / "ai-reviewer-b-decision.json"
        ),
        "prohibited_information_boundary": {
            "ai_reviewer_a_vector": True,
            "ai_reviewer_a_reasoning": True,
            "ai_reviewer_a_outcome": True,
            "ai_reviewer_a_focal_hypothesis": True,
            "ai_reviewer_a_source_condition_finding": True,
            "combined_result": True,
            "final_outcome": True,
            "admission_status": True,
            "scoring_or_gold_labels": True,
            "unrelated_candidate_outcomes": True,
            "future_queue_material": True,
            "track_b_material": True,
        },
        "terminal_record_published": False,
        "ledger_updated": False,
    }
    assignment_path = position_dir / "ai-reviewer-b-assignment.json"
    assignment_path.write_text(json.dumps(assignment))
    with pytest.raises(runner.RunnerError, match="prohibited A/outcome material"):
        repo.validate_assignment(assignment_path, runner.Role.AI_SECOND_REVIEW)


def test_25_lock_prevents_second_track_a_runner(tmp_path: Path) -> None:
    lock_path = tmp_path / "track-a-runner.lock"
    with lock_path.open("w") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        process = subprocess.run(
            [str(RUNNER_ROOT / "run-track-a.fish"), "--dry-run"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "TRACK_A_RUNNER_ROOT": str(tmp_path)},
            check=False,
        )
    assert process.returncode == 73
    assert "another Track A autonomous runner" in process.stderr


def test_26_every_logical_role_uses_unique_invocation_identity() -> None:
    repo = FakeRepository(reviewer_b_required=True)
    _, executor, _ = run_fake(repo)
    identities = [identity for _, _, identity in executor.invocations]
    assert len(identities) == len(set(identities)) == 5


def test_27_next_position_controller_never_starts_before_terminal() -> None:
    repo = FakeRepository(controller_terminal="AUTO_MECHANICAL_REJECT")
    outcome, executor, _ = run_fake(repo, max_positions=2)
    controller_positions = [
        position
        for position, role, _ in executor.invocations
        if role is runner.Role.POSITION_CONTROLLER
    ]
    assert outcome.positions_completed == 2
    assert controller_positions == [22, 23]
    assert 22 in repo.terminals


def test_28_dry_run_render_is_nonmutating_and_exact() -> None:
    class DryRepository:
        amendment_path = REPOSITORY_ROOT / runner.AMENDMENT_RELATIVE_PATH

        def phase(self, position: int) -> runner.Phase:
            return runner.Phase.NEED_CONTROLLER

    class DryExecutor:
        model = runner.DEFAULT_CODEX_MODEL
        profile = None

        def _controller_command(self) -> list[str]:
            return [
                "codex",
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "-",
            ]

        def render_prompt(
            self, role: runner.Role, position: int, expected_head: str
        ) -> str:
            return f"exact-controller-{position}-{expected_head}\n"

    snapshot = FakeRepository().snapshot()
    before = snapshot
    report = runner.render_dry_run(
        DryRepository(), DryExecutor(), snapshot, 25  # type: ignore[arg-type]
    )
    assert snapshot == before
    assert "classification=DRY_RUN" in report
    assert "BEGIN_EXACT_POSITION_CONTROLLER_PROMPT" in report
    assert "position_controller_invocation=" in report
    assert "--dangerously-bypass-approvals-and-sandbox" in report
    assert "codex_role_invocations=0" in report


def test_29_max_position_bound_does_not_change_scientific_stop() -> None:
    repo = FakeRepository(controller_terminal="AUTO_MECHANICAL_REJECT")
    outcome, _, _ = run_fake(repo, max_positions=2)
    assert outcome.classification is runner.Classification.MAX_POSITION_STOP
    assert outcome.positions_completed == 2
    assert repo.global_action == "CONTINUE"


def test_30_outer_state_machine_never_requests_candidate_semantics() -> None:
    source = inspect.getsource(runner.StateMachine.run)
    assert "candidate" not in source.lower()
    assert "evidence" not in source.lower()
    assert "review_packet" not in source.lower()


def test_31_agreement_preserves_exact_review_outcome() -> None:
    decision = {
        "candidate_id": "candidate",
        "review_packet_sha256": "a" * 64,
        "answers": [{"question_id": "Q1", "answer": "YES"}],
        "outcome": "REVIEW_RETAIN",
        "focal_hypothesis": {"hypothesis_id": "one"},
    }
    assert runner.combine_review_metadata(decision, decision) == (
        "REVIEW_RETAIN",
        "AGREEMENT",
    )


def test_32_resume_and_fork_tokens_are_prohibited_by_executor_source() -> None:
    source = inspect.getsource(runner.CodexRoleExecutor._run_process)
    assert '"resume" in command' in source
    assert '"fork" in command' in source


def test_33_fake_codex_roles_are_distinct_os_processes(tmp_path: Path) -> None:
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type': 'thread.started', 'thread_id': str(os.getpid())}))\n"
    )
    fake_codex.chmod(0o755)
    executor = runner.CodexRoleExecutor.__new__(runner.CodexRoleExecutor)
    executor.model = runner.DEFAULT_CODEX_MODEL
    executor.profile = None
    executions = []
    for attempt in (1, 2):
        role_dir = tmp_path / f"attempt-{attempt}"
        role_dir.mkdir()
        executions.append(
            executor._run_process(
                [str(fake_codex)],
                cwd=tmp_path,
                role=runner.Role.POSITION_CONTROLLER,
                position=22,
                prompt="bounded fake prompt\n",
                prompt_digest="a" * 64,
                invocation_id=str(uuid.uuid4()),
                started="2026-08-28T00:00:00Z",
                role_dir=role_dir,
                last_message_path=None,
            )
        )
    assert all(item.exit_code == 0 for item in executions)
    assert executions[0].codex_thread_id != executions[1].codex_thread_id
    assert executions[0].invocation_id != executions[1].invocation_id


def test_34_generated_command_uses_valid_unattended_cli_shape(tmp_path: Path) -> None:
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "sys.stdin.read()\n"
        "arguments = sys.argv[1:]\n"
        "if '--sandbox' in arguments and '--approve-for-me' in arguments:\n"
        "    print('incompatible option combination', file=sys.stderr)\n"
        "    raise SystemExit(64)\n"
        "print(json.dumps({'type': 'thread.started', "
        "'thread_id': 'fake-cli-regression', 'arguments': arguments}))\n"
    )
    fake_codex.chmod(0o755)

    class CommandRepository:
        worktree = tmp_path

    executor = runner.CodexRoleExecutor.__new__(runner.CodexRoleExecutor)
    executor.repository = CommandRepository()
    executor.codex_bin = fake_codex.resolve()
    executor.model = runner.DEFAULT_CODEX_MODEL
    executor.profile = None
    role_dir = tmp_path / "role-output"
    role_dir.mkdir()
    execution = executor._execute_controller(
        runner.Role.POSITION_CONTROLLER,
        7,
        "bounded fake prompt\n",
        "a" * 64,
        str(uuid.uuid4()),
        "2026-08-29T00:00:00Z",
        role_dir,
    )

    assert execution.exit_code == 0
    arguments = json.loads(execution.stdout)["arguments"]
    assert arguments == [
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--color",
        "never",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "gpt-5.6-sol",
        "--cd",
        str(tmp_path),
        "-",
    ]
    assert "--sandbox" not in arguments
    assert "--approve-for-me" not in arguments
    reviewer_source = inspect.getsource(
        runner.CodexRoleExecutor._execute_isolated_reviewer
    )
    assert "*self._base_codex_arguments()" in reviewer_source
    assert '"--sandbox"' not in reviewer_source
    assert '"--approve-for-me"' not in reviewer_source


def test_35_append_only_cli_correction_binds_old_and_new_hashes() -> None:
    correction_path = REPOSITORY_ROOT / runner.CORRECTION_RELATIVE_PATH
    manifest = json.loads((correction_path / "freeze-manifest.json").read_text())
    correction = json.loads(
        (correction_path / "operational-amendment.json").read_text()
    )
    base_path = REPOSITORY_ROOT / runner.AMENDMENT_RELATIVE_PATH

    assert manifest["correction_id"] == runner.CORRECTION_ID
    assert correction["correction_id"] == runner.CORRECTION_ID
    assert correction["effective_from_position"] == 22
    assert correction["position_22_unopened"]["authorization_absent"] is True
    assert correction["scientific_methodology_changed"] is False
    assert correction["reviewer_authority_changed_from_base_amendment"] is False
    assert correction["base_amendment"]["freeze_manifest_sha256"] == (
        runner.sha256_file(base_path / "freeze-manifest.json")
    )
    assert correction["base_amendment"]["operational_amendment_sha256"] == (
        runner.sha256_file(base_path / "operational-amendment.json")
    )
    assert manifest["superseded_external_runner_artifacts"] == correction[
        "old_external_runner_artifacts"
    ]
    assert manifest["external_runner_artifacts"] == correction[
        "corrected_external_runner_artifacts"
    ]
    for artifact in manifest["artifacts"]:
        assert runner.sha256_file(REPOSITORY_ROOT / artifact["path"]) == artifact[
            "sha256"
        ]
    # The v0.1 CLI correction remains immutable historical evidence.  A later
    # append-only durable-orchestration amendment may supersede its live paths;
    # in that case it must preserve this exact predecessor list and bind the new
    # live hashes explicitly.
    new_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "durable-autonomous-orchestration-v0.1/freeze-manifest.json"
    )
    lifecycle_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-runner-lifecycle-correction-v0.1/freeze-manifest.json"
    )
    integrity_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-runner-preproduction-integrity-correction-v0.1/"
        "freeze-manifest.json"
    )
    network_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-runner-network-recovery-correction-v0.1/"
        "freeze-manifest.json"
    )
    structured_output_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-ai-review-structured-output-correction-v0.1/"
        "freeze-manifest.json"
    )
    evidence_reference_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-ai-review-evidence-reference-correction-v0.1/"
        "freeze-manifest.json"
    )
    canonical_reconciliation_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "autonomous-ai-review-canonical-reconciliation-correction-v0.1/"
        "freeze-manifest.json"
    )
    topology_correction_manifest_path = REPOSITORY_ROOT / (
        "benchmark-selection/screening/operational-amendments/"
        "position-materialization-topology-correction-v0.1/"
        "freeze-manifest.json"
    )
    if new_manifest_path.exists():
        new_manifest = json.loads(new_manifest_path.read_text())
        assert new_manifest["superseded_external_runner_artifacts"] == manifest[
            "external_runner_artifacts"
        ]
        effective_manifest = new_manifest
        if lifecycle_manifest_path.exists():
            lifecycle_manifest = json.loads(lifecycle_manifest_path.read_text())
            assert lifecycle_manifest["superseded_external_runner_artifacts"] == (
                new_manifest["external_runner_artifacts"]
            )
            effective_manifest = lifecycle_manifest
            if integrity_manifest_path.exists():
                integrity_manifest = json.loads(integrity_manifest_path.read_text())
                assert integrity_manifest["superseded_external_runner_artifacts"] == (
                    lifecycle_manifest["external_runner_artifacts"]
                )
                effective_manifest = integrity_manifest
                if network_manifest_path.exists():
                    network_manifest = json.loads(network_manifest_path.read_text())
                    assert network_manifest[
                        "superseded_external_runner_artifacts"
                    ] == integrity_manifest["external_runner_artifacts"]
                    assert network_manifest["predecessor_integrity_correction"][
                        "freeze_manifest_sha256"
                    ] == runner.sha256_file(integrity_manifest_path)
                    effective_manifest = network_manifest
                    if structured_output_manifest_path.exists():
                        structured_manifest = json.loads(
                            structured_output_manifest_path.read_text()
                        )
                        assert structured_manifest[
                            "superseded_external_runner_artifacts"
                        ] == network_manifest["external_runner_artifacts"]
                        assert structured_manifest[
                            "predecessor_network_correction"
                        ]["freeze_manifest_sha256"] == runner.sha256_file(
                            network_manifest_path
                        )
                        effective_manifest = structured_manifest
                        if evidence_reference_manifest_path.exists():
                            evidence_manifest = json.loads(
                                evidence_reference_manifest_path.read_text()
                            )
                            assert evidence_manifest[
                                "superseded_external_runner_artifacts"
                            ] == structured_manifest[
                                "external_runner_artifacts"
                            ]
                            assert evidence_manifest[
                                "predecessor_structured_output_correction"
                            ]["freeze_manifest_sha256"] == runner.sha256_file(
                                structured_output_manifest_path
                            )
                            effective_manifest = evidence_manifest
                            if canonical_reconciliation_manifest_path.exists():
                                canonical_manifest = json.loads(
                                    canonical_reconciliation_manifest_path.read_text()
                                )
                                assert canonical_manifest[
                                    "superseded_external_runner_artifacts"
                                ] == evidence_manifest["external_runner_artifacts"]
                                assert canonical_manifest[
                                    "predecessor_evidence_reference_correction"
                                ]["freeze_manifest_sha256"] == runner.sha256_file(
                                    evidence_reference_manifest_path
                                )
                                effective_manifest = canonical_manifest
                                if topology_correction_manifest_path.exists():
                                    topology_manifest = json.loads(
                                        topology_correction_manifest_path.read_text()
                                    )
                                    assert topology_manifest[
                                        "superseded_external_runner_artifacts"
                                    ] == canonical_manifest[
                                        "external_runner_artifacts"
                                    ]
                                    assert topology_manifest[
                                        "predecessor_canonical_reconciliation_correction"
                                    ]["freeze_manifest_sha256"] == runner.sha256_file(
                                        canonical_reconciliation_manifest_path
                                    )
                                    effective_manifest = topology_manifest
        for artifact in effective_manifest["external_runner_artifacts"]:
            assert runner.sha256_file(Path(artifact["path"])) == artifact["sha256"]
    else:
        for artifact in manifest["external_runner_artifacts"]:
            assert runner.sha256_file(Path(artifact["path"])) == artifact["sha256"]

    if new_manifest_path.exists():
        import track_a_runner_v2

        repository = track_a_runner_v2.ProductionRepositoryV2.__new__(
            track_a_runner_v2.ProductionRepositoryV2
        )
        repository.worktree = REPOSITORY_ROOT
        repository.amendment_path = base_path
        repository.correction_path = correction_path
        repository.new_amendment_path = new_manifest_path.parent
        repository.lifecycle_correction_path = lifecycle_manifest_path.parent
        repository.engineering_correction_path = integrity_manifest_path.parent
        repository.network_correction_path = network_manifest_path.parent
        repository.structured_output_correction_path = (
            structured_output_manifest_path.parent
        )
        repository.evidence_reference_correction_path = (
            evidence_reference_manifest_path.parent
        )
        repository.canonical_reconciliation_correction_path = (
            canonical_reconciliation_manifest_path.parent
        )
        repository.topology_correction_path = topology_correction_manifest_path.parent
        state_manifest_path = next(
            path
            for path in (
                topology_correction_manifest_path,
                canonical_reconciliation_manifest_path,
                evidence_reference_manifest_path,
                structured_output_manifest_path,
                network_manifest_path,
                integrity_manifest_path,
                lifecycle_manifest_path,
                new_manifest_path,
            )
            if path.exists()
        )
        repository.state = {
            "amendment_manifest_sha256": runner.sha256_file(state_manifest_path)
        }
        verified = repository._verify_amendment_chain()
        if topology_correction_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.TOPOLOGY_CORRECTION_ID
            )
        elif canonical_reconciliation_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.CANONICAL_RECONCILIATION_CORRECTION_ID
            )
        elif evidence_reference_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.EVIDENCE_REFERENCE_CORRECTION_ID
            )
        elif structured_output_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.STRUCTURED_OUTPUT_CORRECTION_ID
            )
        elif network_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.NETWORK_CORRECTION_ID
            )
        elif integrity_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.ENGINEERING_CORRECTION_ID
            )
        elif lifecycle_manifest_path.exists():
            assert verified["correction_id"] == (
                track_a_runner_v2.LIFECYCLE_CORRECTION_ID
            )
        else:
            assert verified["amendment_id"] == track_a_runner_v2.NEW_AMENDMENT_ID
    else:
        repository = runner.ProductionRepository.__new__(runner.ProductionRepository)
        repository.worktree = REPOSITORY_ROOT
        repository.amendment_path = base_path
        repository.correction_path = correction_path
        repository.state = {
            "amendment_manifest_sha256": runner.sha256_file(
                correction_path / "freeze-manifest.json"
            )
        }
        verified_base = repository._verify_amendment()
        assert verified_base["amendment_id"] == runner.AMENDMENT_ID

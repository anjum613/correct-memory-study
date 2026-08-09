from __future__ import annotations

import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from urllib.request import urlopen

import pytest

from cmpilot.qwen36_candidate import MODEL_REVISION, SELECTED_CONTEXT_LENGTH, sha256_file
from cmpilot.qwen36_qualification import ALL_TASKS, QUALIFICATION_FREEZE, SEED_SCHEDULE
from scripts.generate_qwen36_qualification_batches import (
    TECHNICAL_RERUN_TASK,
    render,
)
from scripts.qwen36_server_port import (
    LOOPBACK_HOST,
    MAX_BIND_ATTEMPTS,
    MIN_PORT,
    PORT_COUNT,
    base_url,
    candidate_port,
    candidate_schedule,
    inspect_vllm_019_port_contract,
    is_explicit_pre_model_address_in_use,
)


ROOT = Path(__file__).parents[1]
QWEN_ENV = Path("/home/s224049759/environments/qwen36-vllm-v1")
P01_SEED = 1602021252
EXACT_BIND_FAILURE = """(APIServer pid=1) Traceback (most recent call last):
  File "api_server.py", line 669, in run_server
    listen_address, sock = setup_server(args)
  File "api_server.py", line 548, in setup_server
    sock = create_server_socket(sock_addr)
  File "api_server.py", line 496, in create_server_socket
    sock.bind(addr)
(APIServer pid=1) OSError: [Errno 98] Address already in use
"""


def _seeds() -> dict[str, int]:
    return json.loads((ROOT / SEED_SCHEDULE).read_text(encoding="utf-8"))["seeds"]


def test_job_local_candidate_schedule_is_bounded_distinct_and_stable() -> None:
    assert MAX_BIND_ATTEMPTS == 4
    assert candidate_schedule("25954") == candidate_schedule(25954)
    assert len(set(candidate_schedule("25954"))) == MAX_BIND_ATTEMPTS
    assert candidate_schedule("25954")[0] != candidate_schedule("25955")[0]
    assert all(
        MIN_PORT <= port < MIN_PORT + PORT_COUNT
        for port in candidate_schedule("99999999999999999999")
    )
    assert base_url(candidate_port("25954", 1)).startswith("http://127.0.0.1:")


@pytest.mark.parametrize("job_id", ("", "0", "-1", "not-a-job"))
def test_invalid_job_ids_fail_closed(job_id: str) -> None:
    with pytest.raises(ValueError):
        candidate_schedule(job_id)


@pytest.mark.parametrize("attempt", (0, 5))
def test_out_of_budget_attempts_fail_closed(attempt: int) -> None:
    with pytest.raises(ValueError):
        candidate_port("25954", attempt)


def test_only_exact_pre_model_eaddrinuse_is_retryable() -> None:
    assert is_explicit_pre_model_address_in_use(EXACT_BIND_FAILURE, 1) is True
    assert is_explicit_pre_model_address_in_use(EXACT_BIND_FAILURE, 0) is False
    assert (
        is_explicit_pre_model_address_in_use(
            EXACT_BIND_FAILURE.replace("Address already in use", "Connection refused"),
            1,
        )
        is False
    )
    assert (
        is_explicit_pre_model_address_in_use(
            EXACT_BIND_FAILURE + "Loading model weights\n",
            1,
        )
        is False
    )


def test_helper_cli_writes_machine_readable_schedule(tmp_path: Path) -> None:
    record = tmp_path / "schedule.json"
    completed = subprocess.run(
        (
            sys.executable,
            str(ROOT / "scripts/qwen36_server_port.py"),
            "schedule",
            "--job-id",
            "25954",
            "--record",
            str(record),
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    value = json.loads(record.read_text(encoding="utf-8"))
    assert completed.returncode == 0
    assert value["host"] == LOOPBACK_HOST
    assert value["candidate_ports"] == list(candidate_schedule("25954"))
    assert value["max_bind_attempts"] == MAX_BIND_ATTEMPTS
    assert value["retry_condition"] == "exact pre-model EADDRINUSE only"


def test_node_local_claim_prevents_aliasing_active_qualification_endpoints(
    tmp_path: Path,
) -> None:
    job_a = 25_953
    job_b = job_a + PORT_COUNT
    assert candidate_port(job_a, 1) == candidate_port(job_b, 1)
    first_lock = (tmp_path / f"{candidate_port(job_a, 1)}.lock").open("w")
    alias_lock = (tmp_path / f"{candidate_port(job_b, 1)}.lock").open("w")
    second_lock = (tmp_path / f"{candidate_port(job_b, 2)}.lock").open("w")
    try:
        fcntl.flock(first_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            fcntl.flock(alias_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(second_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert candidate_port(job_b, 2) != candidate_port(job_a, 1)
    finally:
        first_lock.close()
        alias_lock.close()
        second_lock.close()


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"ok" if self.path == "/health" else b"missing"
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def test_two_adjacent_mock_jobs_have_independent_loopback_endpoints() -> None:
    servers: list[ThreadingHTTPServer] = []
    for candidate_job in range(410_000, 410_100):
        ports = (candidate_port(candidate_job, 1), candidate_port(candidate_job + 1, 1))
        if ports[0] == ports[1]:
            continue
        try:
            servers = []
            for port in ports:
                servers.append(ThreadingHTTPServer((LOOPBACK_HOST, port), _HealthHandler))
        except OSError:
            for server in servers:
                server.server_close()
            servers = []
            continue
        break
    if len(servers) != 2:
        pytest.skip("no pair of candidate ports was free for the loopback mock")
    threads = [Thread(target=server.serve_forever, daemon=True) for server in servers]
    try:
        for thread in threads:
            thread.start()
        for server in servers:
            port = server.server_address[1]
            with urlopen(f"{base_url(port)}/health", timeout=2) as response:
                assert response.status == 200
                assert response.read() == b"ok"
        assert servers[0].server_address != servers[1].server_address
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)


def test_all_seven_batches_propagate_one_dynamic_loopback_endpoint() -> None:
    freeze = sha256_file(ROOT / QUALIFICATION_FREEZE)
    for task_id, seed in _seeds().items():
        text = render(task_id, seed, freeze)
        assert "PORT=49786" not in text
        assert "probe.bind" not in text
        assert "MAX_SERVER_BIND_ATTEMPTS=4" in text
        assert 'PORT_LOCK_ROOT=/tmp/cmq-qwen36-$UID-ports' in text
        assert "/usr/bin/flock --exclusive --nonblock" in text
        assert "--host 127.0.0.1" in text
        assert "--port \"$PORT\"" in text
        assert '"$BASE_URL/health"' in text
        assert '"$BASE_URL/v1/models"' in text
        assert '"$BASE_URL/v1"' in text
        assert "classify-bind-failure" in text
        assert "FATAL_SERVER_EXIT" in text
        assert "HEALTH_TIMEOUT" in text
        assert "run_qualification_task.py" in text
        assert "memory treatment" not in text.casefold()


def test_technical_rerun_preserves_lineage_seed_and_scientific_configuration() -> None:
    freeze = sha256_file(ROOT / QUALIFICATION_FREEZE)
    text = render(TECHNICAL_RERUN_TASK, P01_SEED, freeze, technical_rerun=True)
    assert "TECHNICAL_RERUN_OF=25953" in text
    assert "TECHNICAL_RERUN_NUMBER=1" in text
    assert "QUALIFICATION_TASK_ID=qnm-p01-interval-merge" in text
    assert "QUALIFICATION_SEED=1602021252" in text
    assert "TASK_SEED=1602021252" in text
    assert "--max-model-len 32768" in text
    assert "--dtype bfloat16" in text
    assert "--tensor-parallel-size 2" in text
    assert "--reasoning-parser qwen3" in text


def test_installed_vllm_019_contract_when_environment_is_available() -> None:
    api = sorted(
        {
            path.resolve()
            for path in QWEN_ENV.glob(
                "lib/python*/site-packages/vllm/entrypoints/openai/api_server.py"
            )
        }
    )
    argparse_utils = sorted(
        {
            path.resolve()
            for path in QWEN_ENV.glob(
                "lib/python*/site-packages/vllm/utils/argparse_utils.py"
            )
        }
    )
    if len(api) != 1 or len(argparse_utils) != 1:
        pytest.skip("frozen Qwen3.6 vLLM environment is unavailable")
    result = inspect_vllm_019_port_contract(api[0], argparse_utils[0])
    assert result["pass"] is True
    assert result["cli_accepts_kernel_assigned_port_zero"] is False
    assert result["bind_before_engine_setup"] is True


def test_frozen_model_seed_and_suite_identities_are_not_changed() -> None:
    assert MODEL_REVISION == "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
    assert SELECTED_CONTEXT_LENGTH == 32768
    assert set(_seeds()) == set(ALL_TASKS)
    assert _seeds()[TECHNICAL_RERUN_TASK] == P01_SEED
    assert sha256_file(ROOT / "qualification/qwen36-v1/suite-reference.json") == (
        "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf"
    )


def test_submission_and_gate_fail_closed_around_the_port_amendment() -> None:
    submit = (ROOT / "scripts/submit_qwen36_qualification.py").read_text(
        encoding="utf-8"
    )
    gate = (ROOT / "scripts/qwen36_qualification_cpu_gate.py").read_text(
        encoding="utf-8"
    )
    assert "only technical rerun 1 of job 25953 is authorized" in submit
    assert "candidate_schedule(job_id)" in submit
    assert "technical-invalid-qualification-25953.json" in submit
    assert "dynamic_server_port_policy" in gate
    assert "cpu-preflight-qualification-port-fix-25953" in submit
    assert "cpu-preflight-qualification-port-fix-25953" in gate

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cmpilot.adapter_preflight import AdapterPreflightConfig, PASS_CLASSIFICATION, run_adapter_preflight


DEFAULT_MINI_PY = Path("/home/s224049759/environments/mini-swe-agent-smoke/bin/python")


def test_exact_adapter_reaches_first_request_before_dummy_connection_failure(tmp_path: Path) -> None:
    mini_python = Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    artifacts = tmp_path / "adapter-preflight"

    exit_code = run_adapter_preflight(
        AdapterPreflightConfig(
            mini_python=str(mini_python),
            artifact_dir=artifacts,
            timeout_seconds=45,
        )
    )

    result = json.loads((artifacts / "result.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (artifacts / "adapter-events.jsonl").read_text().splitlines()]
    event_names = [event["event"] for event in events]
    trajectory = json.loads((artifacts / "trajectory.json").read_text(encoding="utf-8"))
    initial_hashes = json.loads((artifacts / "initial-file-hashes.json").read_text(encoding="utf-8"))
    final_hashes = json.loads((artifacts / "final-file-hashes.json").read_text(encoding="utf-8"))
    types = json.loads((artifacts / "agent-config-types.json").read_text(encoding="utf-8"))
    policy = json.loads(
        (artifacts / "command-authorization-policy.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert result["classification"] == PASS_CLASSIFICATION
    assert result["expected_error_type"] == "TransportConnectionError"
    assert "Connection refused" in result["expected_error_message"]
    assert event_names == [
        "adapter_started",
        "installed_sources_validated",
        "command_authorization_policy_loaded",
        "task_file_policy_loaded",
        "prompt_safety_validated",
        "configuration_serialized",
        "mini_swe_config_validated",
        "protected_path_baseline_captured",
        "agent_initialized",
            "model_request_attempted",
            "model_request_budgeted",
            "model_request_failed",
        "agent_failed",
    ]
    assert trajectory["info"]["model_stats"]["api_calls"] == 1
    assert trajectory["info"]["exit_status"] == "TransportConnectionError"
    assert initial_hashes == final_hashes
    assert types["$.agent.output_path"] == "pathlib.PosixPath"
    assert not (artifacts / "patch.diff").read_text(encoding="utf-8")
    assert not (artifacts / "git-status.txt").read_text(encoding="utf-8")
    assert not (artifacts / "patch-history.jsonl").exists()
    assert policy["policy_version"] == "calculator-capability-policy-v3"
    assert all(result["checks"].values())

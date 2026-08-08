from __future__ import annotations

import subprocess
from unittest.mock import patch
from pathlib import Path

import pytest

from cmpilot.mini_swe_adapter import (
    ADAPTER_SOURCE,
    EXPECTED_VERSION,
    RUNTIME_ACTION_PROTOCOL_MODULE,
    RUNTIME_TASK_FILE_POLICY_MODULE,
    RUNTIME_HARDENED_AGENT_MODULE,
    METADATA_VERSION_QUERY,
    RUNTIME_CONFIG_MODULE,
    mini_swe_info,
    RUNTIME_MODEL_MODULE,
    RUNTIME_SOURCE_MANIFEST_MODULE,
    RUNTIME_TRANSPORT_MODULE,
    write_adapter,
)


def completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_mini_swe_info_accepts_exact_distribution_version_with_metadata_query() -> None:
    with patch(
        "cmpilot.mini_swe_adapter.subprocess.run",
        return_value=completed_process(stdout=f"{EXPECTED_VERSION}\n"),
    ) as run:
        info = mini_swe_info("/mini-swe/python")

    assert info.available is True
    assert info.version == EXPECTED_VERSION
    assert info.diagnostic == f"mini-SWE-agent {EXPECTED_VERSION}"
    command = run.call_args.args[0]
    assert command == ["/mini-swe/python", "-c", METADATA_VERSION_QUERY]
    assert "from importlib.metadata import PackageNotFoundError, version" in command[2]
    assert "import minisweagent" not in command[2]
    assert ".env" not in command[2]


def test_mini_swe_info_rejects_a_different_distribution_version() -> None:
    with patch("cmpilot.mini_swe_adapter.subprocess.run", return_value=completed_process(stdout="2.4.5\n")):
        info = mini_swe_info("/mini-swe/python")

    assert info.available is False
    assert info.version == "2.4.5"
    assert info.diagnostic == "mini-SWE-agent 2.4.6 required; found 2.4.5"


def test_mini_swe_info_reports_a_missing_distribution() -> None:
    with patch(
        "cmpilot.mini_swe_adapter.subprocess.run",
        return_value=completed_process(returncode=1, stderr="mini-SWE-agent distribution is not installed\n"),
    ):
        info = mini_swe_info("/mini-swe/python")

    assert info.available is False
    assert info.version == ""
    assert info.diagnostic == "mini-SWE-agent distribution is not installed"


def test_mini_swe_info_reports_a_nonzero_metadata_query() -> None:
    with patch(
        "cmpilot.mini_swe_adapter.subprocess.run",
        return_value=completed_process(returncode=1, stderr="metadata query failed\n"),
    ):
        info = mini_swe_info("/mini-swe/python")

    assert info.available is False
    assert info.version == ""
    assert info.diagnostic == "metadata query failed"


@pytest.mark.parametrize("output", ["", "mini-SWE-agent 2.4.6\n", "2.4.6\nextra"])
def test_mini_swe_info_rejects_empty_or_malformed_version_output(output: str) -> None:
    with patch("cmpilot.mini_swe_adapter.subprocess.run", return_value=completed_process(stdout=output)):
        info = mini_swe_info("/mini-swe/python")

    assert info.available is False
    assert "invalid semantic version" in info.diagnostic


def test_adapter_matches_the_shipped_text_action_config_and_smoke_limits() -> None:
    assert "VllmTextModel" in ADAPTER_SOURCE
    assert "LitellmTextbasedModel" not in ADAPTER_SOURCE
    assert "AuditedLocalEnvironment" in ADAPTER_SOURCE
    assert 'CMPILOT_PATCH_HISTORY' in ADAPTER_SOURCE
    assert 'CMPILOT_AGENT_CONFIG_SOURCE' in ADAPTER_SOURCE
    assert '"api_key"' not in ADAPTER_SOURCE
    assert "local-smoke-placeholder" not in ADAPTER_SOURCE


def test_adapter_uses_strict_config_boundary_before_agent_initialization() -> None:
    assert "build_mini_swe_config" in ADAPTER_SOURCE
    assert "deterministic_json(raw_mini_config)" in ADAPTER_SOURCE
    assert "yaml.safe_dump" in ADAPTER_SOURCE
    assert "yaml.safe_load" in ADAPTER_SOURCE
    assert "AgentConfig(**mini_config" in ADAPTER_SOURCE
    assert "LocalEnvironmentConfig(**mini_config" in ADAPTER_SOURCE
    assert "VllmTextModelConfig(**model_settings)" in ADAPTER_SOURCE
    assert "get_model_class" in ADAPTER_SOURCE
    assert 'emit_event("agent_initialized")' in ADAPTER_SOURCE
    assert 'CMPILOT_MODEL_TRANSPORT_ARTIFACT' in ADAPTER_SOURCE
    assert "recursive_merge" not in ADAPTER_SOURCE


def test_write_adapter_preserves_the_canonical_runtime_helper(tmp_path: Path) -> None:
    adapter = tmp_path / "mini_swe_adapter.py"
    write_adapter(adapter)
    helper = tmp_path / RUNTIME_CONFIG_MODULE
    assert adapter.read_text(encoding="utf-8") == ADAPTER_SOURCE
    assert helper.is_file()
    for name in (
        RUNTIME_ACTION_PROTOCOL_MODULE,
        RUNTIME_TASK_FILE_POLICY_MODULE,
        RUNTIME_HARDENED_AGENT_MODULE,
        RUNTIME_MODEL_MODULE,
        RUNTIME_TRANSPORT_MODULE,
        RUNTIME_SOURCE_MANIFEST_MODULE,
    ):
        assert (tmp_path / name).is_file()

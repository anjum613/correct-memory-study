"""Verified project-owned runtime adapter for mini-SWE-agent 2.4.6."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXPECTED_VERSION = "2.4.6"
RUNTIME_ACTION_PROTOCOL_MODULE = "cmpilot_action_protocol.py"
RUNTIME_COMMAND_AUTHORIZATION_MODULE = "cmpilot_command_authorization.py"
RUNTIME_COMMAND_GATEWAY_MODULE = "cmpilot_command_gateway.py"
RUNTIME_FILESYSTEM_SANDBOX_MODULE = "cmpilot_filesystem_sandbox.py"
RUNTIME_TASK_FILE_POLICY_MODULE = "cmpilot_task_file_policy.py"
RUNTIME_HARDENED_AGENT_MODULE = "cmpilot_hardened_agent.py"
RUNTIME_CONFIG_MODULE = "cmpilot_mini_swe_config.py"
RUNTIME_MODEL_MODULE = "cmpilot_vllm_text_model.py"
RUNTIME_TRANSPORT_MODULE = "cmpilot_openai_transport.py"
RUNTIME_CONTEXT_BUDGET_MODULE = "cmpilot_context_budget.py"
RUNTIME_SOURCE_MANIFEST_MODULE = "cmpilot_mini_swe_sources.py"
_INTEGRATION_ROOT = Path(__file__).with_name("integrations") / "miniswe"
SEMANTIC_VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
METADATA_VERSION_QUERY = '''from importlib.metadata import PackageNotFoundError, version

try:
    print(version("mini-swe-agent"))
except PackageNotFoundError:
    raise SystemExit("mini-SWE-agent distribution is not installed")
'''


@dataclass(frozen=True)
class MiniSWEInfo:
    available: bool
    version: str
    diagnostic: str


# This follows mini-SWE-agent v2.4.6's documented Python API. The installed
# default.yaml prompt uses fenced text actions, so the project-owned direct model
# reuses mini-SWE's text parser instead of its native tool-call parser. DefaultAgent
# avoids interactive confirmation and saves its native trajectory. Each run receives
# an exact source snapshot rather than importing the cmpilot environment.
ADAPTER_SOURCE = (_INTEGRATION_ROOT / "adapter_runtime.py").read_text(encoding="utf-8")


def mini_swe_info(mini_python: str) -> MiniSWEInfo:
    """Inspect the requested interpreter without importing it into cmpilot itself."""
    if not mini_python:
        return MiniSWEInfo(False, "", "MINI_SWE_PYTHON or --mini-python is required")
    try:
        result = subprocess.run(
            [mini_python, "-c", METADATA_VERSION_QUERY],
            text=True,
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        return MiniSWEInfo(False, "", f"mini-SWE-agent Python not found: {mini_python}")
    except subprocess.TimeoutExpired:
        return MiniSWEInfo(False, "", "timed out checking mini-SWE-agent")
    except OSError as error:
        return MiniSWEInfo(False, "", f"could not check mini-SWE-agent: {error}")

    if result.returncode != 0:
        return MiniSWEInfo(False, "", result.stderr.strip() or "mini-SWE-agent metadata query failed")
    version = result.stdout.strip()
    if not SEMANTIC_VERSION.fullmatch(version):
        return MiniSWEInfo(
            False,
            version,
            f"mini-SWE-agent metadata query returned invalid semantic version: {version or 'empty output'}",
        )
    if version != EXPECTED_VERSION:
        return MiniSWEInfo(False, version, f"mini-SWE-agent {EXPECTED_VERSION} required; found {version or 'unknown'}")
    return MiniSWEInfo(True, version, f"mini-SWE-agent {version}")


def write_adapter(path: Path) -> None:
    """Snapshot every project-owned runtime module beside the adapter."""
    path.write_text(ADAPTER_SOURCE, encoding="utf-8")
    sources = {
        RUNTIME_ACTION_PROTOCOL_MODULE: _INTEGRATION_ROOT / "action_protocol.py",
        RUNTIME_COMMAND_AUTHORIZATION_MODULE: _INTEGRATION_ROOT / "command_authorization.py",
        RUNTIME_COMMAND_GATEWAY_MODULE: _INTEGRATION_ROOT / "command_gateway.py",
        RUNTIME_FILESYSTEM_SANDBOX_MODULE: _INTEGRATION_ROOT / "filesystem_sandbox.py",
        RUNTIME_TASK_FILE_POLICY_MODULE: Path(__file__).with_name("task_file_policy.py"),
        RUNTIME_HARDENED_AGENT_MODULE: _INTEGRATION_ROOT / "hardened_agent.py",
        RUNTIME_CONFIG_MODULE: Path(__file__).with_name("mini_swe_config.py"),
        RUNTIME_MODEL_MODULE: _INTEGRATION_ROOT / "vllm_text_model.py",
        RUNTIME_TRANSPORT_MODULE: _INTEGRATION_ROOT / "openai_transport.py",
        RUNTIME_CONTEXT_BUDGET_MODULE: _INTEGRATION_ROOT / "context_budget.py",
        RUNTIME_SOURCE_MANIFEST_MODULE: _INTEGRATION_ROOT / "source_manifest.py",
    }
    for destination, source in sources.items():
        path.with_name(destination).write_text(
            source.read_text(encoding="utf-8"), encoding="utf-8"
        )


def command(mini_python: str, adapter_path: Path) -> list[str]:
    return [mini_python, str(adapter_path)]

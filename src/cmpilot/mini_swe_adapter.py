"""Verified mini-SWE-agent 2.4.6 adapter for a local one-shot smoke run."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


EXPECTED_VERSION = "2.4.6"


@dataclass(frozen=True)
class MiniSWEInfo:
    available: bool
    version: str
    diagnostic: str


# This follows mini-SWE-agent v2.4.6's documented Python example.  Its
# LitellmModel supplies the native Bash tool schema; no interactive CLI mode is
# used, and output_path causes DefaultAgent to save its native trajectory.
ADAPTER_SOURCE = '''import logging
import os
from pathlib import Path

import yaml
from minisweagent import __version__, package_dir
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.litellm_model import LitellmModel

repository = Path(os.environ["CMPILOT_REPOSITORY"])
task = Path(os.environ["CMPILOT_TASK_FILE"]).read_text(encoding="utf-8")
trajectory = Path(os.environ["CMPILOT_TRAJECTORY"])
agent_config = yaml.safe_load((Path(package_dir) / "config" / "default.yaml").read_text(encoding="utf-8"))["agent"]
agent_config["output_path"] = trajectory

logging.basicConfig(level=logging.INFO)
model = LitellmModel(
    model_name="openai/" + os.environ["CMPILOT_MODEL"],
    model_kwargs={
        "api_base": os.environ["CMPILOT_BASE_URL"],
        "api_key": "local-smoke-placeholder",
        "temperature": 0,
        "drop_params": True,
    },
    cost_tracking="ignore_errors",
)
agent = DefaultAgent(model, LocalEnvironment(cwd=str(repository)), **agent_config)
print("mini-SWE-agent version: " + __version__)
agent.run(task)
'''


def mini_swe_info(mini_python: str) -> MiniSWEInfo:
    """Inspect the requested interpreter without importing it into cmpilot itself."""
    if not mini_python:
        return MiniSWEInfo(False, "", "MINI_SWE_PYTHON or --mini-python is required")
    try:
        result = subprocess.run(
            [mini_python, "-c", "import minisweagent; print(minisweagent.__version__)"],
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

    version = result.stdout.strip()
    if result.returncode != 0:
        return MiniSWEInfo(False, version, result.stderr.strip() or "mini-SWE-agent import failed")
    if version != EXPECTED_VERSION:
        return MiniSWEInfo(False, version, f"mini-SWE-agent {EXPECTED_VERSION} required; found {version or 'unknown'}")
    return MiniSWEInfo(True, version, f"mini-SWE-agent {version}")


def write_adapter(path: Path) -> None:
    path.write_text(ADAPTER_SOURCE, encoding="utf-8")


def command(mini_python: str, adapter_path: Path) -> list[str]:
    return [mini_python, str(adapter_path)]

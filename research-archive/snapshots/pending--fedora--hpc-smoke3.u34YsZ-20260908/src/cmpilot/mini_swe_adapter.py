"""Verified mini-SWE-agent 2.4.6 adapter for a local one-shot smoke run."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXPECTED_VERSION = "2.4.6"
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
# default.yaml prompt uses fenced text actions, so it is paired with the
# supported LitellmTextbasedModel rather than the native tool-call parser.
# DefaultAgent avoids interactive confirmation and saves its native trajectory.
ADAPTER_SOURCE = '''import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import yaml
from minisweagent import __version__, package_dir
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel
from minisweagent.utils.serialize import recursive_merge


class AuditedLocalEnvironment(LocalEnvironment):
    def __init__(self, *, repository: Path, audit_path: Path, **kwargs):
        super().__init__(**kwargs)
        self.repository = repository
        self.audit_path = audit_path
        self.command_index = 0

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict:
        self.command_index += 1
        started = time.time()
        output = None
        exception_name = ""
        try:
            output = super().execute(action, cwd=cwd, timeout=timeout)
            return output
        except BaseException as error:
            exception_name = type(error).__name__
            raise
        finally:
            patch = subprocess.run(
                ["git", "-C", str(self.repository), "diff", "--binary", "HEAD", "--"],
                text=True,
                capture_output=True,
                check=False,
            ).stdout
            record = {
                "command_index": self.command_index,
                "started_at_epoch": started,
                "finished_at_epoch": time.time(),
                "command": action.get("command", ""),
                "returncode": None if output is None else output.get("returncode"),
                "stdout_stderr": "" if output is None else output.get("output", ""),
                "exception": exception_name,
                "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
                "patch": patch,
            }
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\\n")

repository = Path(os.environ["CMPILOT_REPOSITORY"])
task = Path(os.environ["CMPILOT_TASK_FILE"]).read_text(encoding="utf-8")
trajectory = Path(os.environ["CMPILOT_TRAJECTORY"])
patch_history = Path(os.environ["CMPILOT_PATCH_HISTORY"])
base_config = yaml.safe_load((Path(package_dir) / "config" / "default.yaml").read_text(encoding="utf-8"))
smoke_config = yaml.safe_load(Path(os.environ["CMPILOT_AGENT_CONFIG_SOURCE"]).read_text(encoding="utf-8"))
resolved_config = recursive_merge(base_config, smoke_config)

agent_config = resolved_config["agent"]
agent_config["output_path"] = trajectory
environment_config = resolved_config["environment"]
environment_config["cwd"] = str(repository)
environment_config["env"] = environment_config.get("env", {}) | {
    "PATH": os.environ["CMPILOT_AGENT_PATH"],
    "HOME": os.environ["HOME"],
    "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"],
    "TMPDIR": os.environ["TMPDIR"],
    "OPENAI_API_KEY": "",
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
model_config = resolved_config["model"]
model_config["model_name"] = "openai/" + os.environ["CMPILOT_MODEL"]
model_config["model_kwargs"] = model_config.get("model_kwargs", {}) | {
    "api_base": os.environ["CMPILOT_BASE_URL"],
    "temperature": 0,
    "drop_params": True,
}

artifact_config = {
    "agent": agent_config,
    "environment": environment_config,
    "model": model_config,
}
Path(os.environ["CMPILOT_AGENT_CONFIG_ARTIFACT"]).write_text(
    yaml.safe_dump(artifact_config, sort_keys=False), encoding="utf-8"
)

logging.basicConfig(level=logging.INFO)
model = LitellmTextbasedModel(**model_config)
environment = AuditedLocalEnvironment(
    repository=repository,
    audit_path=patch_history,
    **environment_config,
)
agent = DefaultAgent(model, environment, **agent_config)
print("mini-SWE-agent version: " + __version__)
result = agent.run(task)
print(json.dumps({"agent_result": result, "model_calls": agent.n_calls}, sort_keys=True))
'''


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
    path.write_text(ADAPTER_SOURCE, encoding="utf-8")


def command(mini_python: str, adapter_path: Path) -> list[str]:
    return [mini_python, str(adapter_path)]

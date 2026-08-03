"""Verified mini-SWE-agent 2.4.6 adapter for a local one-shot smoke run."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXPECTED_VERSION = "2.4.6"
RUNTIME_CONFIG_MODULE = "cmpilot_mini_swe_config.py"
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
from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
from minisweagent.models.litellm_textbased_model import (
    LitellmTextbasedModel,
    LitellmTextbasedModelConfig,
)

from cmpilot_mini_swe_config import (
    MiniSWEEndpointSettings,
    assert_no_sensitive_keys,
    build_mini_swe_config,
    describe_data_types,
    deterministic_json,
    validate_plain_data,
)


def emit_event(event: str, **details) -> None:
    record = {"event": event, "time_epoch": time.time(), **details}
    with Path(os.environ["CMPILOT_ADAPTER_EVENTS"]).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\\n")


class AuditedLitellmTextbasedModel(LitellmTextbasedModel):
    def _query(self, messages: list[dict[str, str]], **kwargs):
        emit_event("model_request_attempted")
        try:
            return super()._query(messages, **kwargs)
        except BaseException as error:
            emit_event(
                "model_request_failed",
                exception_type=type(error).__name__,
                message=str(error),
            )
            raise


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

emit_event("adapter_started", mini_swe_version=__version__)
repository = Path(os.environ["CMPILOT_REPOSITORY"])
task_file = Path(os.environ["CMPILOT_TASK_FILE"])
task = task_file.read_text(encoding="utf-8")
trajectory = Path(os.environ["CMPILOT_TRAJECTORY"])
patch_history = Path(os.environ["CMPILOT_PATCH_HISTORY"])
preflight_mode = os.environ.get("CMPILOT_ADAPTER_PREFLIGHT") == "1"

# These layers are intentionally separate. Only mini_config is passed to
# mini-SWE-agent; cmpilot run and artifact metadata never cross that boundary.
cmpilot_run_metadata = {
    "repository": repository,
    "task_file": task_file,
    "preflight_mode": preflight_mode,
}
endpoint_settings = MiniSWEEndpointSettings(
    base_url=os.environ["CMPILOT_BASE_URL"],
    model=os.environ["CMPILOT_MODEL"],
    request_timeout_seconds=2.0 if preflight_mode else None,
    max_retries=0 if preflight_mode else None,
)
artifact_metadata = {
    "trajectory": trajectory,
    "patch_history": patch_history,
    "agent_config_yaml": Path(os.environ["CMPILOT_AGENT_CONFIG_ARTIFACT"]),
    "agent_config_json": Path(os.environ["CMPILOT_AGENT_CONFIG_JSON_ARTIFACT"]),
}

base_config = yaml.safe_load((Path(package_dir) / "config" / "default.yaml").read_text(encoding="utf-8"))
smoke_config = yaml.safe_load(Path(os.environ["CMPILOT_AGENT_CONFIG_SOURCE"]).read_text(encoding="utf-8"))
raw_mini_config = build_mini_swe_config(
    base_config,
    smoke_config,
    endpoint=endpoint_settings,
    repository=repository,
    trajectory=trajectory,
    agent_environment={
    "PATH": os.environ["CMPILOT_AGENT_PATH"],
    "HOME": os.environ["HOME"],
    "XDG_CONFIG_HOME": os.environ["XDG_CONFIG_HOME"],
    "TMPDIR": os.environ["TMPDIR"],
    "PYTHONNOUSERSITE": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    },
)

# Record every pre-conversion type. In particular, output_path is deliberately
# a pathlib.Path here and is converted by the one canonical boundary function.
_, type_text = deterministic_json(describe_data_types(raw_mini_config))
Path(os.environ["CMPILOT_AGENT_CONFIG_TYPES_ARTIFACT"]).write_text(type_text, encoding="utf-8")
mini_config, json_text = deterministic_json(raw_mini_config)
assert_no_sensitive_keys(mini_config)
Path(os.environ["CMPILOT_AGENT_CONFIG_JSON_ARTIFACT"]).write_text(json_text, encoding="utf-8")

yaml_text = yaml.safe_dump(mini_config, sort_keys=True, allow_unicode=True)
yaml_round_trip = yaml.safe_load(yaml_text)
validate_plain_data(yaml_round_trip)
assert_no_sensitive_keys(yaml_round_trip)
_, yaml_as_json = deterministic_json(yaml_round_trip)
if yaml_as_json != json_text:
    raise ValueError("safe YAML round trip changed the mini-SWE configuration")
Path(os.environ["CMPILOT_AGENT_CONFIG_ARTIFACT"]).write_text(yaml_text, encoding="utf-8")

# Validate with the exact Pydantic configuration models used by the selected
# mini-SWE-agent classes. This catches schema errors before any model request.
validated_agent = AgentConfig(**mini_config["agent"])
validated_environment = LocalEnvironmentConfig(**mini_config["environment"])
validated_model = LitellmTextbasedModelConfig(**mini_config["model"])
loader_validation = {
    "agent_class": "minisweagent.agents.default.AgentConfig",
    "agent": validated_agent.model_dump(mode="json"),
    "environment_class": "minisweagent.environments.local.LocalEnvironmentConfig",
    "environment": validated_environment.model_dump(mode="json"),
    "model_class": "minisweagent.models.litellm_textbased_model.LitellmTextbasedModelConfig",
    "model": validated_model.model_dump(mode="json"),
    "yaml_round_trip_equal": True,
    "json_round_trip_equal": True,
}
assert_no_sensitive_keys(loader_validation)
_, loader_text = deterministic_json(loader_validation)
Path(os.environ["CMPILOT_LOADER_VALIDATION_ARTIFACT"]).write_text(loader_text, encoding="utf-8")

for destination, value in (
    (os.environ["CMPILOT_RUN_METADATA_ARTIFACT"], cmpilot_run_metadata),
    (os.environ["CMPILOT_ENDPOINT_CONFIG_ARTIFACT"], endpoint_settings),
    (os.environ["CMPILOT_ARTIFACT_METADATA_ARTIFACT"], artifact_metadata),
):
    plain_value, value_text = deterministic_json(value)
    assert_no_sensitive_keys(plain_value)
    Path(destination).write_text(value_text, encoding="utf-8")
emit_event("configuration_serialized")
emit_event("mini_swe_config_validated")

logging.basicConfig(level=logging.INFO)
model = AuditedLitellmTextbasedModel(**mini_config["model"])
environment = AuditedLocalEnvironment(
    repository=repository,
    audit_path=patch_history,
    **mini_config["environment"],
)
agent = DefaultAgent(model, environment, **mini_config["agent"])
emit_event("agent_initialized")
print("mini-SWE-agent version: " + __version__)
try:
    result = agent.run(task)
except BaseException as error:
    emit_event("agent_failed", exception_type=type(error).__name__, message=str(error))
    raise
emit_event("agent_completed", model_calls=agent.n_calls)
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
    """Write the adapter and an exact copy of its canonical config helper."""
    path.write_text(ADAPTER_SOURCE, encoding="utf-8")
    helper_source = Path(__file__).with_name("mini_swe_config.py")
    path.with_name(RUNTIME_CONFIG_MODULE).write_text(helper_source.read_text(encoding="utf-8"), encoding="utf-8")


def command(mini_python: str, adapter_path: Path) -> list[str]:
    return [mini_python, str(adapter_path)]

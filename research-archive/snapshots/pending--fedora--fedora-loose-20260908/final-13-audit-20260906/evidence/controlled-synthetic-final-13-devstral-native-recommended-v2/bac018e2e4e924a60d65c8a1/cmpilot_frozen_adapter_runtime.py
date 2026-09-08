"""Runtime entry point copied into each immutable mini-SWE smoke run."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import yaml
from minisweagent import __version__, package_dir
from minisweagent.agents.default import AgentConfig
from minisweagent.environments.local import LocalEnvironment, LocalEnvironmentConfig
from minisweagent.models import get_model_class

from cmpilot_action_protocol import (
    ACTION_REGEX,
    FORMAT_ERROR_TEMPLATE,
    INITIAL_SYSTEM_TEMPLATE,
    INSTANCE_TEMPLATE,
    INVALID_ACTION_TEMPLATE,
    NATIVE_TOOL_INSTANCE_TEMPLATE,
    NATIVE_TOOL_RECOVERY_PROMPT,
    NATIVE_TOOL_SYSTEM_TEMPLATE,
    PROTOCOL_LIMIT_MESSAGE,
    prompt_match_report,
    render_recovery_prompt,
)
from cmpilot_command_authorization import policy_specification
from cmpilot_hardened_agent import HardenedDefaultAgent
from cmpilot_task_file_policy import calculator_task_policy
from cmpilot_mini_swe_config import (
    MiniSWEEndpointSettings,
    assert_no_sensitive_keys,
    build_mini_swe_config,
    describe_data_types,
    deterministic_json,
    validate_plain_data,
)
from cmpilot_mini_swe_sources import require_installed_sources_unchanged
from cmpilot_vllm_text_model import VllmTextModel, VllmTextModelConfig


def emit_event(event: str, **details: object) -> None:
    record = {"event": event, "time_epoch": time.time(), **details}
    with Path(os.environ["CMPILOT_ADAPTER_EVENTS"]).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


class AuditedLocalEnvironment(LocalEnvironment):
    def __init__(self, *, repository: Path, audit_path: Path, **kwargs: object):
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
                handle.write(json.dumps(record, sort_keys=True) + "\n")


emit_event("adapter_started", mini_swe_version=__version__)
source_manifest = require_installed_sources_unchanged()
Path(os.environ["CMPILOT_MINI_SOURCE_MANIFEST_ARTIFACT"]).write_text(
    json.dumps(source_manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
emit_event("installed_sources_validated")
command_policy = policy_specification()
Path(os.environ["CMPILOT_COMMAND_POLICY_ARTIFACT"]).write_text(
    json.dumps(command_policy, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
emit_event("command_authorization_policy_loaded", policy_version=command_policy["policy_version"])
task_file_policy = calculator_task_policy()
Path(os.environ["CMPILOT_TASK_POLICY_ARTIFACT"]).write_text(
    json.dumps(task_file_policy.as_dict(), indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
emit_event("task_file_policy_loaded", task_policy_version=task_file_policy.version)

repository = Path(os.environ["CMPILOT_REPOSITORY"])
task_file = Path(os.environ["CMPILOT_TASK_FILE"])
task = task_file.read_text(encoding="utf-8")
trajectory = Path(os.environ["CMPILOT_TRAJECTORY"])
patch_history = Path(os.environ["CMPILOT_PATCH_HISTORY"])
transport_artifact = Path(os.environ["CMPILOT_MODEL_TRANSPORT_ARTIFACT"])
request_budget_artifact = Path(os.environ["CMPILOT_REQUEST_BUDGET_ARTIFACT"])
event_path = Path(os.environ["CMPILOT_ADAPTER_EVENTS"])
preflight_mode = os.environ.get("CMPILOT_ADAPTER_PREFLIGHT") == "1"

cmpilot_run_metadata = {
    "repository": repository,
    "task_file": task_file,
    "preflight_mode": preflight_mode,
}
endpoint_settings = MiniSWEEndpointSettings(
    base_url=os.environ["CMPILOT_BASE_URL"],
    model=os.environ["CMPILOT_MODEL"],
    tokenizer_path=os.environ["CMPILOT_TOKENIZER_PATH"],
    request_timeout_seconds=2.0 if preflight_mode else None,
    max_retries=0,
)
artifact_metadata = {
    "trajectory": trajectory,
    "patch_history": patch_history,
    "model_transport": transport_artifact,
    "request_budgets": request_budget_artifact,
    "agent_config_yaml": Path(os.environ["CMPILOT_AGENT_CONFIG_ARTIFACT"]),
    "agent_config_json": Path(os.environ["CMPILOT_AGENT_CONFIG_JSON_ARTIFACT"]),
    "command_authorization_policy": Path(os.environ["CMPILOT_COMMAND_POLICY_ARTIFACT"]),
    "task_file_policy": Path(os.environ["CMPILOT_TASK_POLICY_ARTIFACT"]),
}

base_config = yaml.safe_load(
    (Path(package_dir) / "config" / "default.yaml").read_text(encoding="utf-8")
)
smoke_config = yaml.safe_load(
    Path(os.environ["CMPILOT_AGENT_CONFIG_SOURCE"]).read_text(encoding="utf-8")
)
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
    transport_artifact=transport_artifact,
    request_budget_artifact=request_budget_artifact,
    event_path=event_path,
)
native_tool_calls = bool(raw_mini_config["model"].get("native_tool_calls", False))
if "CMPILOT_MODEL_SEED" in os.environ:
    raw_mini_config["model"]["seed"] = int(os.environ["CMPILOT_MODEL_SEED"])
raw_mini_config["agent"]["system_template"] = (
    NATIVE_TOOL_SYSTEM_TEMPLATE if native_tool_calls else INITIAL_SYSTEM_TEMPLATE
)
raw_mini_config["agent"]["instance_template"] = (
    NATIVE_TOOL_INSTANCE_TEMPLATE if native_tool_calls else INSTANCE_TEMPLATE
)
raw_mini_config["model"]["action_regex"] = ACTION_REGEX
raw_mini_config["model"]["format_error_template"] = (
    NATIVE_TOOL_RECOVERY_PROMPT if native_tool_calls else FORMAT_ERROR_TEMPLATE
)
active_system_template = raw_mini_config["agent"]["system_template"]
active_instance_template = raw_mini_config["agent"]["instance_template"]
prompt_matches = prompt_match_report(
    {
        "initial_system": active_system_template,
        "instance": active_instance_template.replace("{{task}}", task),
        "format_error_recovery": raw_mini_config["model"]["format_error_template"],
        "invalid_content_recovery": INVALID_ACTION_TEMPLATE,
        "protocol_limit": PROTOCOL_LIMIT_MESSAGE,
        "realistic_recovery": render_recovery_prompt(
            event="INVALID_ACTION_CONTENT",
            action_count=1,
            validation_reason="exact placeholder",
        ),
    }
)
if prompt_matches["initial_system"] > 1 or any(
    count for name, count in prompt_matches.items() if name != "initial_system"
):
    raise ValueError(f"unsafe harness-authored prompt parser matches: {prompt_matches}")
emit_event("prompt_safety_validated", parser_match_counts=prompt_matches)


_, type_text = deterministic_json(describe_data_types(raw_mini_config))
Path(os.environ["CMPILOT_AGENT_CONFIG_TYPES_ARTIFACT"]).write_text(
    type_text, encoding="utf-8"
)
mini_config, json_text = deterministic_json(raw_mini_config)
assert_no_sensitive_keys(mini_config)
Path(os.environ["CMPILOT_AGENT_CONFIG_JSON_ARTIFACT"]).write_text(
    json_text, encoding="utf-8"
)

yaml_text = yaml.safe_dump(mini_config, sort_keys=True, allow_unicode=True)
yaml_round_trip = yaml.safe_load(yaml_text)
validate_plain_data(yaml_round_trip)
assert_no_sensitive_keys(yaml_round_trip)
_, yaml_as_json = deterministic_json(yaml_round_trip)
if yaml_as_json != json_text:
    raise ValueError("safe YAML round trip changed the mini-SWE configuration")
Path(os.environ["CMPILOT_AGENT_CONFIG_ARTIFACT"]).write_text(
    yaml_text, encoding="utf-8"
)

validated_agent = AgentConfig(**mini_config["agent"])
validated_environment = LocalEnvironmentConfig(**mini_config["environment"])
model_settings = dict(mini_config["model"])
model_class_path = model_settings.pop("model_class")
model_class = get_model_class(model_settings["model_name"], model_class_path)
if model_class is not VllmTextModel:
    raise TypeError(f"unexpected direct model class: {model_class!r}")
validated_model = VllmTextModelConfig(**model_settings)
loader_validation = {
    "agent_class": "cmpilot_hardened_agent.HardenedDefaultAgent",
    "agent": validated_agent.model_dump(mode="json"),
    "environment_class": "minisweagent.environments.local.LocalEnvironmentConfig",
    "environment": validated_environment.model_dump(mode="json"),
    "model_class": model_class_path,
    "model": validated_model.model_dump(mode="json"),
    "yaml_round_trip_equal": True,
    "json_round_trip_equal": True,
}
assert_no_sensitive_keys(loader_validation)
_, loader_text = deterministic_json(loader_validation)
Path(os.environ["CMPILOT_LOADER_VALIDATION_ARTIFACT"]).write_text(
    loader_text, encoding="utf-8"
)

for destination, value in (
    (os.environ["CMPILOT_RUN_METADATA_ARTIFACT"], cmpilot_run_metadata),
    (os.environ["CMPILOT_ENDPOINT_CONFIG_ARTIFACT"], endpoint_settings),
    (os.environ["CMPILOT_ARTIFACT_METADATA_ARTIFACT"], artifact_metadata),
):
    plain_value, value_text = deterministic_json(value)
    assert_no_sensitive_keys(plain_value)
    Path(destination).write_text(value_text, encoding="utf-8")
emit_event("configuration_serialized")
emit_event("mini_swe_config_validated", model_class=model_class_path)

logging.basicConfig(level=logging.INFO)
model = model_class(**model_settings)
environment = AuditedLocalEnvironment(
    repository=repository,
    audit_path=patch_history,
    **mini_config["environment"],
)
agent = HardenedDefaultAgent(
    model,
    environment,
    repository=repository,
    event_sink=emit_event,
    task_policy=task_file_policy,
    **mini_config["agent"],
)
emit_event("agent_initialized")
print("mini-SWE-agent version: " + __version__)
try:
    result = agent.run(task)
except BaseException as error:
    emit_event("agent_failed", exception_type=type(error).__name__, message=str(error))
    raise
emit_event("agent_completed", model_calls=agent.n_calls)
print(json.dumps({"agent_result": result, "model_calls": agent.n_calls}, sort_keys=True))

"""Immutable model identities for the final shared experiment harness.

This module deliberately keeps model-specific serving details separate from the
scientific action boundary.  A model profile can select an interpreter,
tokenizer, and exact server command, but it cannot replace the production
parser, authorization policy, hardened agent, or total finalizer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .calculator_finalizer import (
    FINALIZER_CONTROL_FLOW_VERSION,
    FINALIZER_STATE_SCHEMA,
)
from .guided_backend import (
    build_qwen32b_server_command,
    offline_environment,
    validate_lm_format_enforcer_command,
)
from .integrations.miniswe.action_protocol import (
    ACTION_REGEX,
    COMPLETION_SENTINEL,
    MAX_CONSECUTIVE_PROTOCOL_ERRORS,
)
from .integrations.miniswe.command_authorization import POLICY_VERSION
from .integrations.miniswe.context_budget import (
    PINNED_TOKENIZER_CONFIG_SHA256,
    PINNED_TOKENIZER_JSON_SHA256,
)
from .integrations.miniswe.source_manifest import EXPECTED_VERSION as MINI_SWE_VERSION
from .qualification import (
    CMPILOT_PYTHON,
    MINI_SWE_PYTHON,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    VLLM_PYTHON,
)
from .server_command import validate_qwen32b_server_command
from .task_file_policy import TASK_POLICY_SCHEMA


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ModelProfileError(ValueError):
    """A model profile or one of its immutable inputs is invalid."""


def _validate_sha256(value: str, *, label: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise ModelProfileError(f"{label} must be a lowercase SHA-256 digest")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class FrozenProjectFile:
    """One project-relative input whose content is part of the protocol."""

    relative_path: Path
    sha256: str

    def __post_init__(self) -> None:
        if self.relative_path.is_absolute() or not self.relative_path.parts:
            raise ModelProfileError("frozen project paths must be non-empty and relative")
        if ".." in self.relative_path.parts:
            raise ModelProfileError("frozen project paths must not escape the project")
        _validate_sha256(self.sha256, label=str(self.relative_path))

    def verify(self, project_root: Path) -> Path:
        root = project_root.resolve(strict=True)
        path = (root / self.relative_path).resolve(strict=True)
        try:
            path.relative_to(root)
        except ValueError as error:
            raise ModelProfileError(
                f"frozen project input escapes project root: {self.relative_path}"
            ) from error
        if not path.is_file():
            raise ModelProfileError(f"frozen project input is not a file: {path}")
        actual = _file_sha256(path)
        if actual != self.sha256:
            raise ModelProfileError(
                f"frozen project input changed: {self.relative_path}; "
                f"expected {self.sha256}, found {actual}"
            )
        return path


@dataclass(frozen=True)
class RuntimeEnvironmentIdentity:
    """Pinned interpreter and installed-content identity for one model server."""

    environment_id: str
    server_python: Path
    controller_python: Path
    agent_python: Path
    environment_fingerprint: str
    environment_content_digest: str
    package_versions: tuple[tuple[str, str], ...]
    offline_environment: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not self.environment_id.strip():
            raise ModelProfileError("environment_id must not be empty")
        for label, path in (
            ("server_python", self.server_python),
            ("controller_python", self.controller_python),
            ("agent_python", self.agent_python),
        ):
            if not path.is_absolute():
                raise ModelProfileError(f"{label} must be an absolute path")
        _validate_sha256(
            self.environment_fingerprint, label="environment_fingerprint"
        )
        _validate_sha256(
            self.environment_content_digest, label="environment_content_digest"
        )
        if tuple(sorted(self.package_versions)) != self.package_versions:
            raise ModelProfileError("package_versions must be sorted")
        if tuple(sorted(self.offline_environment)) != self.offline_environment:
            raise ModelProfileError("offline_environment must be sorted")


@dataclass(frozen=True)
class SerializationIdentity:
    """Tokenizer and chat-template assets used to serialize model requests."""

    tokenizer_path: Path
    assets: tuple[tuple[str, str], ...]
    serialization_mode: str
    chat_template_source: str
    add_generation_prompt: bool

    def __post_init__(self) -> None:
        if not self.tokenizer_path.is_absolute():
            raise ModelProfileError("tokenizer_path must be absolute")
        if not self.assets:
            raise ModelProfileError("serialization assets must not be empty")
        if not self.serialization_mode.strip() or not self.chat_template_source.strip():
            raise ModelProfileError(
                "serialization_mode and chat_template_source must not be empty"
            )
        names: list[str] = []
        for name, digest in self.assets:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ModelProfileError(
                    f"serialization asset must be a safe relative path: {name!r}"
                )
            _validate_sha256(digest, label=f"serialization asset {name}")
            names.append(name)
        if len(set(names)) != len(names):
            raise ModelProfileError("serialization asset names must be unique")

    def asset_sha256(self, name: str) -> str:
        try:
            return dict(self.assets)[name]
        except KeyError as error:
            raise ModelProfileError(f"serialization asset is not frozen: {name}") from error

    @property
    def tokenizer_json_sha256(self) -> str:
        """Qwen convenience accessor; other serializers need not use this asset."""
        return self.asset_sha256("tokenizer.json")

    @property
    def tokenizer_config_sha256(self) -> str:
        """Qwen convenience accessor; other serializers need not use this asset."""
        return self.asset_sha256("tokenizer_config.json")

    def verify(self) -> tuple[Path, ...]:
        verified: list[Path] = []
        for name, expected in self.assets:
            path = self.tokenizer_path / name
            if not path.is_file():
                raise ModelProfileError(f"tokenizer asset is not a file: {path}")
            actual = _file_sha256(path)
            if actual != expected:
                raise ModelProfileError(
                    f"tokenizer asset changed: {path}; expected {expected}, found {actual}"
                )
            verified.append(path)
        return tuple(verified)


@dataclass(frozen=True)
class GenerationSettings:
    """Sampling fields that may cross the ordinary chat-completions boundary."""

    temperature: float
    max_tokens: int
    top_p: float | None = None
    top_k: int | None = None
    min_p: float | None = None
    presence_penalty: float | None = None
    repetition_penalty: float | None = None
    request_seed: int | None = None
    samples_per_call: int | None = None
    stop_tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.temperature < 0 or self.max_tokens < 1:
            raise ModelProfileError("generation temperature/tokens are invalid")
        if self.samples_per_call not in (None, 1):
            raise ModelProfileError("the production adapter permits at most one sample")

    def ordinary_request_parameters(self) -> tuple[tuple[str, int | float], ...]:
        """Return only fields actually sent by the frozen Qwen request path."""
        parameters: list[tuple[str, int | float]] = [
            ("temperature", self.temperature),
            ("max_tokens", self.max_tokens),
        ]
        for key, value in (
            ("top_p", self.top_p),
            ("top_k", self.top_k),
            ("min_p", self.min_p),
            ("presence_penalty", self.presence_penalty),
            ("repetition_penalty", self.repetition_penalty),
            ("seed", self.request_seed),
            ("n", self.samples_per_call),
        ):
            if value is not None:
                parameters.append((key, value))
        return tuple(parameters)


@dataclass(frozen=True)
class ServerSettings:
    dtype: str
    tensor_parallel_size: int
    max_model_length: int
    max_num_sequences: int
    gpu_memory_utilization: str
    server_seed: int
    quantization: str | None = None


@dataclass(frozen=True)
class ScientificBoundaryIdentity:
    """Identity shared by every evaluated model; profiles cannot override it."""

    action_regex: str
    completion_sentinel: str
    maximum_consecutive_protocol_errors: int
    hardened_agent_class: str
    command_policy_version: str
    task_policy_schema: str
    mini_swe_agent_version: str
    finalizer_state_schema: str
    finalizer_control_flow_version: str
    source_files: tuple[FrozenProjectFile, ...]

    def verify(self, project_root: Path) -> tuple[Path, ...]:
        return tuple(item.verify(project_root) for item in self.source_files)


PRODUCTION_AGENT_CONFIG = FrozenProjectFile(
    Path("configs/agent/mini_swe_agent_smoke.yaml"),
    "a4396981a64a5823672e908a2b9c1e488a23a0b8b726624fe86bc935c6ca1ac0",
)

PRODUCTION_SCIENTIFIC_BOUNDARY = ScientificBoundaryIdentity(
    action_regex=ACTION_REGEX,
    completion_sentinel=COMPLETION_SENTINEL,
    maximum_consecutive_protocol_errors=MAX_CONSECUTIVE_PROTOCOL_ERRORS,
    hardened_agent_class=(
        "cmpilot.integrations.miniswe.hardened_agent.HardenedDefaultAgent"
    ),
    command_policy_version=POLICY_VERSION,
    task_policy_schema=TASK_POLICY_SCHEMA,
    mini_swe_agent_version=MINI_SWE_VERSION,
    finalizer_state_schema=FINALIZER_STATE_SCHEMA,
    finalizer_control_flow_version=FINALIZER_CONTROL_FLOW_VERSION,
    source_files=(
        FrozenProjectFile(
            Path("src/cmpilot/integrations/miniswe/action_protocol.py"),
            "8f27eebcaa2f2a7b8d38dafcea4701ef748746a38dcb1f4c5d96da8920a60555",
        ),
        FrozenProjectFile(
            Path("src/cmpilot/integrations/miniswe/hardened_agent.py"),
            "04afe18dfae680f5936d7df7b3c360ec61027b2a9f667fc54c9eaaae5b023178",
        ),
        FrozenProjectFile(
            Path("src/cmpilot/integrations/miniswe/command_authorization.py"),
            "35bc1887b151953955d520eecfa75be47c8d668953257f72a37bb4f4327ab8b3",
        ),
        FrozenProjectFile(
            Path("src/cmpilot/task_file_policy.py"),
            "c9c89c682b44cf7a9304e96b14286a7c6e90af8af81eaaf6a0e698b293a4b006",
        ),
        FrozenProjectFile(
            Path("src/cmpilot/calculator_finalizer.py"),
            "34a979c8d55318585cd2e7357e1cb586df0f8d1e403eaab416ee15f38855ea0e",
        ),
        FrozenProjectFile(
            Path("src/cmpilot/integrations/miniswe/source_manifest.py"),
            "4b5f8e76faede451c13df25b1030a9b55094d810a61466d5e81c4b8d0802911f",
        ),
    ),
)


ServerCommandBuilder = Callable[[int], tuple[str, ...]]
ServerCommandValidator = Callable[[Sequence[str]], tuple[str, ...]]


@dataclass(frozen=True)
class ModelProfile:
    """Small immutable interface between the shared runner and a model server."""

    profile_id: str
    model_id: str
    model_revision: str
    model_snapshot: Path
    served_model_name: str
    environment: RuntimeEnvironmentIdentity
    serialization: SerializationIdentity
    server: ServerSettings
    generation: GenerationSettings
    _server_command_builder: ServerCommandBuilder = field(repr=False, compare=False)
    _server_command_validator: ServerCommandValidator = field(
        repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.model_id.strip():
            raise ModelProfileError("profile_id and model_id must not be empty")
        if re.fullmatch(r"[0-9a-f]{40}", self.model_revision) is None:
            raise ModelProfileError("model_revision must be an immutable Git revision")
        if not self.model_snapshot.is_absolute():
            raise ModelProfileError("model_snapshot must be absolute")
        if not self.served_model_name.strip():
            raise ModelProfileError("served_model_name must not be empty")
        if self.serialization.tokenizer_path != self.model_snapshot:
            raise ModelProfileError(
                "the frozen model and tokenizer snapshot paths must be identical"
            )
        if self.server.max_model_length != 4096:
            raise ModelProfileError("the final experiment context bound must be 4096")
        if self.server.tensor_parallel_size < 1:
            raise ModelProfileError("tensor_parallel_size must be positive")

    @property
    def agent_config(self) -> FrozenProjectFile:
        """Return the single frozen agent configuration shared across models."""
        return PRODUCTION_AGENT_CONFIG

    @property
    def scientific_boundary(self) -> ScientificBoundaryIdentity:
        """Return the non-model-specific production action boundary."""
        return PRODUCTION_SCIENTIFIC_BOUNDARY

    def server_argv(self, *, port: int) -> tuple[str, ...]:
        """Build and then fail-closed validate this profile's server command."""
        command = self._server_command_builder(port)
        return self._server_command_validator(command)

    def validate_server_argv(self, command: Sequence[str]) -> tuple[str, ...]:
        return self._server_command_validator(command)

    def verify_static_inputs(self, project_root: Path) -> tuple[Path, ...]:
        """Verify the prompt/config, tokenizer, and shared boundary before a run."""
        agent_config = self.agent_config.verify(project_root)
        tokenizer_files = self.serialization.verify()
        boundary_files = self.scientific_boundary.verify(project_root)
        return (agent_config, *tokenizer_files, *boundary_files)


def _build_qwen32b_server_argv(port: int) -> tuple[str, ...]:
    return build_qwen32b_server_command(port=port)


def _validate_qwen32b_server_argv(command: Sequence[str]) -> tuple[str, ...]:
    backend_validated = validate_lm_format_enforcer_command(command)
    return validate_qwen32b_server_command(backend_validated)


QWEN32B_PROFILE = ModelProfile(
    profile_id="qwen2.5-coder-32b-instruct",
    model_id=MODEL_ID,
    model_revision=MODEL_REVISION,
    model_snapshot=MODEL_SNAPSHOT,
    served_model_name=str(MODEL_SNAPSHOT),
    environment=RuntimeEnvironmentIdentity(
        environment_id="qwen32b-vllm-smoke-v1",
        server_python=VLLM_PYTHON,
        controller_python=CMPILOT_PYTHON,
        agent_python=MINI_SWE_PYTHON,
        environment_fingerprint=(
            "6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071"
        ),
        environment_content_digest=(
            "5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee"
        ),
        package_versions=(
            ("lm-format-enforcer", "0.10.6"),
            ("python", "3.12.8"),
            ("tokenizers", "0.20.3"),
            ("torch", "2.4.0"),
            ("transformers", "4.45.2"),
            ("vllm", "0.6.1.post2"),
        ),
        offline_environment=tuple(sorted(offline_environment().items())),
    ),
    serialization=SerializationIdentity(
        tokenizer_path=MODEL_SNAPSHOT,
        assets=(
            ("tokenizer.json", PINNED_TOKENIZER_JSON_SHA256),
            ("tokenizer_config.json", PINNED_TOKENIZER_CONFIG_SHA256),
        ),
        serialization_mode="huggingface-chat-template",
        chat_template_source="tokenizer_config.json",
        add_generation_prompt=True,
    ),
    server=ServerSettings(
        dtype="bfloat16",
        tensor_parallel_size=2,
        max_model_length=4096,
        max_num_sequences=1,
        gpu_memory_utilization="0.90",
        server_seed=0,
        quantization=None,
    ),
    generation=GenerationSettings(temperature=0.0, max_tokens=512),
    _server_command_builder=_build_qwen32b_server_argv,
    _server_command_validator=_validate_qwen32b_server_argv,
)


MODEL_PROFILES: Mapping[str, ModelProfile] = MappingProxyType(
    {QWEN32B_PROFILE.profile_id: QWEN32B_PROFILE}
)


def get_model_profile(profile_id: str) -> ModelProfile:
    """Resolve a frozen model profile and fail closed on unknown identifiers."""
    try:
        return MODEL_PROFILES[profile_id]
    except KeyError as error:
        raise ModelProfileError(f"unknown model profile: {profile_id!r}") from error


__all__ = [
    "GenerationSettings",
    "MODEL_PROFILES",
    "ModelProfile",
    "ModelProfileError",
    "PRODUCTION_AGENT_CONFIG",
    "PRODUCTION_SCIENTIFIC_BOUNDARY",
    "QWEN32B_PROFILE",
    "RuntimeEnvironmentIdentity",
    "ScientificBoundaryIdentity",
    "SerializationIdentity",
    "ServerSettings",
    "get_model_profile",
]

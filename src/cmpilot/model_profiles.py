"""Small, explicit model profiles for replication infrastructure."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROFILE_DIRECTORY = Path(__file__).parents[2] / "configs" / "model_profiles"
_NAME = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
_REVISION = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True)
class ModelProfile:
    """Validated identity and launch data for exactly one model snapshot."""

    schema_version: int
    name: str
    profile_kind: str
    candidate: str
    launchable: bool
    model_id: str
    model_revision: str
    tokenizer_id: str
    tokenizer_revision: str
    served_model_name: str
    runtime_environment: str
    environment_spec: str
    memory_scope: str
    reasoning_mode: str
    seed_policy: str
    seed: int
    stop_strings: tuple[str, ...]
    stop_token_ids: tuple[int, ...]
    chat_template: dict[str, Any]
    generation: dict[str, Any]
    guided_decoding: dict[str, Any]
    server: dict[str, Any]
    required_manifest_fields: tuple[str, ...]

    @property
    def identity(self) -> str:
        """Stable, path-safe identity used by run IDs, caches, and logs."""
        return f"{self.name}-{self.model_revision[:12]}"

    @property
    def server_arguments(self) -> tuple[str, ...]:
        return tuple(self.server.get("arguments", ()))

    def manifest_identity(self) -> dict[str, Any]:
        """Return model-specific fields that must accompany every profiled run."""
        return {
            "model_profile_name": self.name,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.tokenizer_revision,
            "served_model_name": self.served_model_name,
            "runtime_environment": self.runtime_environment,
            "environment_spec": self.environment_spec,
            "chat_template": self.chat_template,
            "generation": self.generation,
            "seed_policy": self.seed_policy,
            "seed": self.seed,
            "stop_strings": list(self.stop_strings),
            "stop_token_ids": list(self.stop_token_ids),
            "reasoning_mode": self.reasoning_mode,
            "guided_decoding": self.guided_decoding,
            "server": {key: value for key, value in self.server.items() if key != "arguments"},
            "memory_scope": self.memory_scope,
        }

    def validate(self) -> None:
        """Reject ambiguous identities and unsafe changes to a launchable profile."""
        if self.schema_version != 1:
            raise ValueError(f"unsupported profile schema: {self.schema_version}")
        if not _NAME.fullmatch(self.name):
            raise ValueError(f"invalid model profile name: {self.name}")
        for label, revision in (
            ("model revision", self.model_revision),
            ("tokenizer revision", self.tokenizer_revision),
        ):
            if not _REVISION.fullmatch(revision):
                raise ValueError(f"{label} must be an immutable 40-character commit")
        if not self.model_id or not self.tokenizer_id or not self.served_model_name:
            raise ValueError("model, tokenizer, and served-model identities are required")
        if not self.runtime_environment or not self.required_manifest_fields:
            raise ValueError("runtime environment and manifest fields are required")
        missing_manifest_fields = set(self.required_manifest_fields) - self.manifest_identity().keys()
        if missing_manifest_fields:
            raise ValueError(f"profile cannot emit required manifest fields: {sorted(missing_manifest_fields)}")
        if not self.launchable:
            if self.server_arguments:
                raise ValueError("a non-launchable attestation must not define server arguments")
            return

        arguments = self.server_arguments
        required_pairs = {
            "--revision": self.model_revision,
            "--tokenizer": self.tokenizer_id,
            "--tokenizer-revision": self.tokenizer_revision,
            "--served-model-name": self.served_model_name,
            "--dtype": str(self.server.get("dtype")),
            "--tensor-parallel-size": str(self.server.get("tensor_parallel_size")),
            "--max-model-len": str(self.server.get("maximum_model_length")),
            "--gpu-memory-utilization": str(self.server.get("gpu_memory_utilization")),
            "--seed": str(self.seed),
        }
        if not arguments or arguments[0] != self.model_id:
            raise ValueError("server arguments must launch the attested model ID")
        for option, expected in required_pairs.items():
            if arguments.count(option) != 1:
                raise ValueError(f"server arguments must contain exactly one {option}")
            position = arguments.index(option)
            if position + 1 >= len(arguments) or arguments[position + 1] != expected:
                raise ValueError(f"server argument {option} does not match the profile")
        if self.server.get("quantization") != "none":
            raise ValueError("confirmatory model profiles must not use quantization")
        if "--enable-auto-tool-choice" not in arguments:
            raise ValueError("native tool auto-choice must be explicit")
        parser = self.guided_decoding.get("tool_call_parser")
        if parser is None or ("--tool-call-parser", str(parser)) not in zip(arguments, arguments[1:]):
            raise ValueError("tool-call parser arguments do not match the profile")
        if self.guided_decoding.get("response_rewriting") is not False:
            raise ValueError("model responses must not be rewritten")


def _profile_path(name: str) -> Path:
    if not _NAME.fullmatch(name):
        raise ValueError(f"invalid model profile name: {name}")
    path = PROFILE_DIRECTORY / f"{name}.toml"
    if not path.is_file():
        raise KeyError(f"unknown model profile: {name}")
    return path


def load_model_profile(name: str) -> ModelProfile:
    """Load and validate one repository-owned profile by logical name."""
    with _profile_path(name).open("rb") as profile_file:
        data = tomllib.load(profile_file)
    manifest = data.pop("manifest")
    data["stop_strings"] = tuple(data.get("stop_strings", ()))
    data["stop_token_ids"] = tuple(data.get("stop_token_ids", ()))
    profile = ModelProfile(
        **data,
        required_manifest_fields=tuple(manifest["required_fields"]),
    )
    profile.validate()
    return profile


def available_model_profiles() -> tuple[str, ...]:
    """List committed profiles without inspecting caches or model outputs."""
    return tuple(sorted(path.stem for path in PROFILE_DIRECTORY.glob("*.toml")))

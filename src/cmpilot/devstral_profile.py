"""Fail-closed candidate profile for the isolated Devstral replication.

The serving and agent environments plus exact-revision tokenizer metadata are
staged.  The frozen vLLM Mistral loader's consolidated weight file is
intentionally absent, so this module records the partial attestation but
cannot expose a production-ready ``ModelProfile``.  The separately indexed
ten Hugging Face shards are recorded as an unused alternative and are absent.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Mapping, Sequence

from .experiment_models import (
    PRODUCTION_AGENT_CONFIG,
    PRODUCTION_SCIENTIFIC_BOUNDARY,
    GenerationSettings,
    ScientificBoundaryIdentity,
    ServerSettings,
)


PROFILE_ID = "devstral-small-2507"
MODEL_ID = "mistralai/Devstral-Small-2507"
MODEL_REVISION = "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
SERVED_MODEL_NAME = MODEL_ID

MODEL_CACHE = Path("/home/s224049759/model-cache/huggingface")
MODEL_SNAPSHOT = (
    MODEL_CACHE
    / "hub/models--mistralai--Devstral-Small-2507/snapshots"
    / MODEL_REVISION
)
ENVIRONMENT_ID = "devstral-small-2507-v1"
ENVIRONMENT_PATH = Path("/home/s224049759/environments/devstral-small-2507-v1")
SERVER_PYTHON = ENVIRONMENT_PATH / "bin/python"
CONTROLLER_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
AGENT_PYTHON = Path(
    "/home/s224049759/environments/devstral-small-2507-agent-v1/bin/python"
)
AGENT_ENVIRONMENT_ID = "devstral-small-2507-agent-v1"
AGENT_ENVIRONMENT_PATH = AGENT_PYTHON.parent.parent

CANDIDATE_PYTHON_VERSION = "3.11.11"
CANDIDATE_CUDA_WHEEL_RUNTIME = "12.8"
CANDIDATE_LOCK = Path("configs/environments/devstral-small-2507-lock.txt")
CANDIDATE_LOCK_SHA256 = (
    "f176ebeab5260601c4eef407019fa6afa9039c9be9b337f1f0ededc83a6c1c1e"
)
CANDIDATE_FREEZE = Path("configs/environments/devstral-small-2507-freeze.txt")
CANDIDATE_FREEZE_SHA256 = (
    "a5f4bd7d040151e77b213bac45fa21ef56a0762d655ccec02617ef10b931d184"
)
CANDIDATE_AGENT_LOCK = Path(
    "configs/environments/devstral-small-2507-agent-lock.txt"
)
CANDIDATE_AGENT_LOCK_SHA256 = (
    "c147cc1b8e11706fb657f87d7e3e61b4d5fb90230a2285dfafeb78a8786df755"
)
CANDIDATE_AGENT_FREEZE = Path(
    "configs/environments/devstral-small-2507-agent-freeze.txt"
)
CANDIDATE_AGENT_FREEZE_SHA256 = (
    "fbd5c69216799eb291a2d5864f293c2378722173b8816b56b3468b2d341a5141"
)
CANDIDATE_PACKAGE_VERSIONS = (
    ("huggingface-hub", "0.33.4"),
    ("mistral-common", "1.8.4"),
    ("outlines-core", "0.2.10"),
    ("packaging", "25.0"),
    ("pip", "25.1.1"),
    ("tokenizers", "0.21.2"),
    ("torch", "2.7.1+cu128"),
    ("torchaudio", "2.7.1+cu128"),
    ("torchvision", "0.22.1+cu128"),
    ("transformers", "4.53.2"),
    ("vllm", "0.10.0"),
    ("xgrammar", "0.1.21"),
)
CANDIDATE_AGENT_PACKAGE_VERSIONS = (
    ("litellm", "1.98.0"),
    ("mini-swe-agent", "2.4.6"),
    ("mistral-common", "1.8.4"),
    ("openai", "2.54.0"),
    ("packaging", "25.0"),
    ("pip", "25.1.1"),
    ("tokenizers", "0.23.1"),
)
ENVIRONMENT_FINGERPRINT_SHA256 = (
    "a46d2f6e7c1f40f3429e4729afbc43e1357f82810e9c86f4464b6be7ab7b893d"
)
ENVIRONMENT_CONTENT_DIGEST_SHA256 = (
    "85cd239b14eb746ad2f13e483a61b40434b398ef77eddbbb65a460dd9efb55d8"
)
ENVIRONMENT_CONTENT_DISTRIBUTIONS = (
    "mistral-common",
    "outlines-core",
    "safetensors",
    "tokenizers",
    "torch",
    "transformers",
    "vllm",
    "xgrammar",
)

TOKENIZER_MODE = "mistral"
CONFIG_FORMAT = "mistral"
LOAD_FORMAT = "mistral"
CHAT_TEMPLATE_SOURCE = "mistral-common/tekken.json"
MODEL_SYSTEM_PROMPT = None
NATIVE_TOOL_CALL_PARSER = None
STAGED_SNAPSHOT_FILE_SHA256 = (
    (
        "config.json",
        "868bdb4e07afca5d86dc0a874f11ede7ff586b1aaa6e3edfc2e82ec3ad771a1b",
    ),
    (
        "generation_config.json",
        "86acf1e8f5d32e7c25ce501b6d9b6152f4eaf8659e5cea9907ad58d50ba4cc47",
    ),
    (
        "model.safetensors.index.json",
        "2d570fc53098c04ddc802460b783fbecf0a5b0cf4c4d36e0491a870ad81779fd",
    ),
    (
        "params.json",
        "52abcf3369f5acc22cdd1ab8a6fcb696122e9e906d9a701fd45296a9fd28e8e8",
    ),
    (
        "tekken.json",
        "839c48629ff570bd664586800aa3ee17ee628f56efc7fd8e145cc01467a1c188",
    ),
)
ALTERNATIVE_WEIGHT_SHARD_FILES = tuple(
    f"model-{index:05d}-of-00010.safetensors" for index in range(1, 11)
)
REQUIRED_SNAPSHOT_FILES = (
    "config.json",
    "consolidated.safetensors",
    "generation_config.json",
    "model.safetensors.index.json",
    "params.json",
    "tekken.json",
)
EXPECTED_CONSOLIDATED_SIZE = 47_144_846_024
EXPECTED_CONSOLIDATED_SHA256 = (
    "ed57cdadcdfe28e026bafa56ee1b5c91866e1d85cd33b772c8216415926d5727"
)
ALTERNATIVE_SHARDS_TOTAL_SIZE = 47_144_806_400

SERVER_SETTINGS = ServerSettings(
    dtype="bfloat16",
    tensor_parallel_size=2,
    max_model_length=4096,
    max_num_sequences=1,
    gpu_memory_utilization="0.90",
    server_seed=0,
    quantization=None,
)
GENERATION_SETTINGS = GenerationSettings(temperature=0.0, max_tokens=512)

OFFLINE_ENVIRONMENT = tuple(
    sorted(
        {
            "HF_HOME": str(MODEL_CACHE),
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TOKENIZERS_PARALLELISM": "false",
            "TRANSFORMERS_OFFLINE": "1",
        }.items()
    )
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_NORMALIZE_PACKAGE = re.compile(r"[-_.]+")


class DevstralProfileError(RuntimeError):
    """The Devstral candidate is incomplete or violates its frozen contract."""


def _validate_sha256(value: str, *, label: str) -> None:
    if _SHA256.fullmatch(value) is None:
        raise DevstralProfileError(f"{label} must be a lowercase SHA-256 digest")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_package_name(value: str) -> str:
    """Apply the package-name normalization used for direct-pin comparison."""
    return _NORMALIZE_PACKAGE.sub("-", value).lower()


def validate_candidate_environment(
    *, python_version: str, package_versions: Mapping[str, str]
) -> tuple[str, ...]:
    """Return deterministic reasons a live environment misses candidate pins."""
    errors: list[str] = []
    if python_version != CANDIDATE_PYTHON_VERSION:
        errors.append(
            f"python: expected {CANDIDATE_PYTHON_VERSION}, found {python_version}"
        )
    installed = {
        normalize_package_name(name): version
        for name, version in package_versions.items()
    }
    for name, expected in CANDIDATE_PACKAGE_VERSIONS:
        actual = installed.get(name)
        if actual is None:
            errors.append(f"{name}: not installed")
        elif actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    return tuple(errors)


def validate_candidate_agent_environment(
    *, python_version: str, package_versions: Mapping[str, str]
) -> tuple[str, ...]:
    """Return deterministic reasons the isolated agent prefix misses pins."""
    errors: list[str] = []
    if python_version != CANDIDATE_PYTHON_VERSION:
        errors.append(
            f"python: expected {CANDIDATE_PYTHON_VERSION}, found {python_version}"
        )
    installed = {
        normalize_package_name(name): version
        for name, version in package_versions.items()
    }
    for name, expected in CANDIDATE_AGENT_PACKAGE_VERSIONS:
        actual = installed.get(name)
        if actual is None:
            errors.append(f"{name}: not installed")
        elif actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    return tuple(errors)


@dataclass(frozen=True)
class VerifiedDevstralIdentity:
    """Hashes that may only be populated from staged, captured artifacts."""

    environment_fingerprint_sha256: str
    environment_content_digest_sha256: str
    environment_lock_sha256: str
    snapshot_file_sha256: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        for label, value in (
            ("environment_fingerprint_sha256", self.environment_fingerprint_sha256),
            (
                "environment_content_digest_sha256",
                self.environment_content_digest_sha256,
            ),
            ("environment_lock_sha256", self.environment_lock_sha256),
        ):
            _validate_sha256(value, label=label)
        if tuple(sorted(self.snapshot_file_sha256)) != self.snapshot_file_sha256:
            raise DevstralProfileError("snapshot_file_sha256 must be sorted")
        names = tuple(name for name, _ in self.snapshot_file_sha256)
        if names != REQUIRED_SNAPSHOT_FILES:
            raise DevstralProfileError(
                "snapshot hashes must cover exactly the required Devstral files"
            )
        for name, digest in self.snapshot_file_sha256:
            if Path(name).name != name:
                raise DevstralProfileError(f"unsafe snapshot file name: {name!r}")
            _validate_sha256(digest, label=f"snapshot {name}")


@dataclass(frozen=True)
class DevstralCandidateProfile:
    """Immutable candidate identity; readiness remains explicitly external."""

    profile_id: str = PROFILE_ID
    model_id: str = MODEL_ID
    model_revision: str = MODEL_REVISION
    model_snapshot: Path = MODEL_SNAPSHOT
    served_model_name: str = SERVED_MODEL_NAME
    environment_id: str = ENVIRONMENT_ID
    environment_path: Path = ENVIRONMENT_PATH
    server_python: Path = SERVER_PYTHON
    tokenizer_mode: str = TOKENIZER_MODE
    config_format: str = CONFIG_FORMAT
    load_format: str = LOAD_FORMAT
    chat_template_source: str = CHAT_TEMPLATE_SOURCE
    model_system_prompt: None = MODEL_SYSTEM_PROMPT
    native_tool_call_parser: None = NATIVE_TOOL_CALL_PARSER
    server: ServerSettings = SERVER_SETTINGS
    generation: GenerationSettings = GENERATION_SETTINGS
    verification_state: str = "PARTIAL_METADATA_TOKENIZER_STAGED_WEIGHTS_ABSENT"

    @property
    def agent_config(self):
        return PRODUCTION_AGENT_CONFIG

    @property
    def scientific_boundary(self) -> ScientificBoundaryIdentity:
        return PRODUCTION_SCIENTIFIC_BOUNDARY

    def intended_server_argv(self, *, port: int) -> tuple[str, ...]:
        """Return the strict candidate command without asserting readiness."""
        return build_devstral_server_argv(port=port)

    def server_argv(
        self,
        *,
        port: int,
        verified_identity: VerifiedDevstralIdentity | None = None,
        project_root: Path | None = None,
        snapshot_path: Path | None = None,
        environment_path: Path | None = None,
    ) -> tuple[str, ...]:
        """Return the command only after all staged identities verify."""
        verify_devstral_readiness(
            verified_identity=verified_identity,
            project_root=project_root,
            snapshot_path=snapshot_path,
            environment_path=environment_path,
        )
        return build_devstral_server_argv(port=port)


DEVSTRAL_CANDIDATE = DevstralCandidateProfile()


def _validate_port(port: int) -> None:
    if isinstance(port, bool) or not 1024 <= port <= 65535:
        raise DevstralProfileError("server port must be an unprivileged TCP port")


def build_devstral_server_argv(*, port: int) -> tuple[str, ...]:
    """Build the sole permitted Devstral vLLM command for the experiment."""
    _validate_port(port)
    return (
        str(SERVER_PYTHON),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        str(MODEL_SNAPSHOT),
        "--tokenizer",
        str(MODEL_SNAPSHOT),
        "--served-model-name",
        SERVED_MODEL_NAME,
        "--dtype",
        SERVER_SETTINGS.dtype,
        "--tensor-parallel-size",
        str(SERVER_SETTINGS.tensor_parallel_size),
        "--max-model-len",
        str(SERVER_SETTINGS.max_model_length),
        "--max-num-seqs",
        str(SERVER_SETTINGS.max_num_sequences),
        "--gpu-memory-utilization",
        SERVER_SETTINGS.gpu_memory_utilization,
        "--seed",
        str(SERVER_SETTINGS.server_seed),
        "--enforce-eager",
        "--tokenizer-mode",
        TOKENIZER_MODE,
        "--config-format",
        CONFIG_FORMAT,
        "--load-format",
        LOAD_FORMAT,
        "--generation-config",
        "vllm",
    )


def validate_devstral_server_argv(command: Sequence[str]) -> tuple[str, ...]:
    """Reject every launch mutation except the allocated loopback port."""
    candidate = tuple(command)
    if candidate.count("--port") != 1:
        raise DevstralProfileError("Devstral command must contain exactly one port")
    try:
        port = int(candidate[candidate.index("--port") + 1])
    except (IndexError, ValueError) as error:
        raise DevstralProfileError("Devstral command has an invalid port") from error
    expected = build_devstral_server_argv(port=port)
    if candidate != expected:
        raise DevstralProfileError(
            "Devstral server command differs from the frozen candidate command"
        )
    return candidate


def verify_devstral_readiness(
    *,
    verified_identity: VerifiedDevstralIdentity | None,
    project_root: Path | None = None,
    snapshot_path: Path | None = None,
    environment_path: Path | None = None,
) -> tuple[Path, ...]:
    """Verify staged inputs and refuse readiness when real hashes are unavailable."""
    if verified_identity is None:
        raise DevstralProfileError(
            "Devstral snapshot/environment hashes have not been frozen"
        )
    root = (project_root or Path(__file__).resolve().parents[2]).resolve(strict=True)
    snapshot = (snapshot_path or MODEL_SNAPSHOT).resolve(strict=True)
    environment = (environment_path or ENVIRONMENT_PATH).resolve(strict=True)
    interpreter = environment / "bin/python"
    if not interpreter.is_file():
        raise DevstralProfileError(
            f"Devstral environment interpreter is absent: {interpreter}"
        )

    lock = (root / CANDIDATE_LOCK).resolve(strict=True)
    actual_lock_sha256 = _sha256_file(lock)
    if actual_lock_sha256 != CANDIDATE_LOCK_SHA256:
        raise DevstralProfileError("the checked-in Devstral candidate lock changed")
    if verified_identity.environment_lock_sha256 != actual_lock_sha256:
        raise DevstralProfileError("the staged Devstral environment used another lock")
    freeze = (root / CANDIDATE_FREEZE).resolve(strict=True)
    if _sha256_file(freeze) != CANDIDATE_FREEZE_SHA256:
        raise DevstralProfileError("the checked-in Devstral exact freeze changed")
    if (
        verified_identity.environment_fingerprint_sha256
        != ENVIRONMENT_FINGERPRINT_SHA256
    ):
        raise DevstralProfileError("the staged Devstral environment fingerprint changed")
    if (
        verified_identity.environment_content_digest_sha256
        != ENVIRONMENT_CONTENT_DIGEST_SHA256
    ):
        raise DevstralProfileError("the staged Devstral environment content changed")

    verified_paths: list[Path] = [interpreter, lock, freeze]
    for name, expected_sha256 in verified_identity.snapshot_file_sha256:
        path = snapshot / name
        if not path.is_file():
            raise DevstralProfileError(f"Devstral snapshot file is absent: {path}")
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            raise DevstralProfileError(
                f"Devstral snapshot file changed: {name}; "
                f"expected {expected_sha256}, found {actual_sha256}"
            )
        verified_paths.append(path)
    return tuple(verified_paths)


__all__ = [
    "ALTERNATIVE_SHARDS_TOTAL_SIZE",
    "ALTERNATIVE_WEIGHT_SHARD_FILES",
    "AGENT_ENVIRONMENT_ID",
    "AGENT_ENVIRONMENT_PATH",
    "AGENT_PYTHON",
    "CANDIDATE_AGENT_LOCK",
    "CANDIDATE_AGENT_LOCK_SHA256",
    "CANDIDATE_AGENT_FREEZE",
    "CANDIDATE_AGENT_FREEZE_SHA256",
    "CANDIDATE_AGENT_PACKAGE_VERSIONS",
    "CANDIDATE_CUDA_WHEEL_RUNTIME",
    "CANDIDATE_LOCK",
    "CANDIDATE_LOCK_SHA256",
    "CANDIDATE_FREEZE",
    "CANDIDATE_FREEZE_SHA256",
    "CANDIDATE_PACKAGE_VERSIONS",
    "CANDIDATE_PYTHON_VERSION",
    "CONFIG_FORMAT",
    "CONTROLLER_PYTHON",
    "DEVSTRAL_CANDIDATE",
    "DevstralCandidateProfile",
    "DevstralProfileError",
    "ENVIRONMENT_ID",
    "ENVIRONMENT_PATH",
    "ENVIRONMENT_CONTENT_DIGEST_SHA256",
    "ENVIRONMENT_CONTENT_DISTRIBUTIONS",
    "ENVIRONMENT_FINGERPRINT_SHA256",
    "EXPECTED_CONSOLIDATED_SHA256",
    "EXPECTED_CONSOLIDATED_SIZE",
    "LOAD_FORMAT",
    "MODEL_ID",
    "MODEL_REVISION",
    "MODEL_SNAPSHOT",
    "NATIVE_TOOL_CALL_PARSER",
    "OFFLINE_ENVIRONMENT",
    "PROFILE_ID",
    "REQUIRED_SNAPSHOT_FILES",
    "SERVER_PYTHON",
    "SERVED_MODEL_NAME",
    "TOKENIZER_MODE",
    "STAGED_SNAPSHOT_FILE_SHA256",
    "VerifiedDevstralIdentity",
    "build_devstral_server_argv",
    "normalize_package_name",
    "validate_candidate_agent_environment",
    "validate_candidate_environment",
    "validate_devstral_server_argv",
    "verify_devstral_readiness",
]

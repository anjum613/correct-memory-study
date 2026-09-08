"""Fail-closed candidate and qualified production profiles for Devstral.

The serving and agent environments, exact-revision tokenizer metadata, and
the Mistral loader's consolidated runtime weight are staged.  Readiness still
requires the repository-owned snapshot freeze and live environment verifier.
The separately indexed Hugging Face shards remain an unused alternative.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Mapping, Sequence

from .experiment_models import (
    FrozenProjectFile,
    ModelProfile,
    PRODUCTION_AGENT_CONFIG,
    PRODUCTION_SCIENTIFIC_BOUNDARY,
    GenerationSettings,
    RuntimeEnvironmentIdentity,
    ScientificBoundaryIdentity,
    SerializationIdentity,
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

SNAPSHOT_FREEZE = Path("qualification/devstral-small-2507-snapshot-freeze.json")
SNAPSHOT_FREEZE_SHA256 = (
    "2486602a374814152283f8a48fb6a0108bc5c96eeabf17a6e911cf8107e4a011"
)
SNAPSHOT_FREEZE_IDENTITY_SHA256 = (
    "7341bd8b1c9f1556fa39465e9b51b931ba1433d2fa23d1253d5f71b0739b6128"
)
SNAPSHOT_IDENTITY_SHA256 = (
    "e90b3af5301c42112c1711c919851aefd4c366bfc237c022c641add7ab7c8eaf"
)
TECHNICAL_SMOKE_JOB_ID = "28589"
TECHNICAL_SMOKE_RESULT = Path(
    "/home/s224049759/final-experiment-artifacts/"
    "devstral-small-2507-technical-smoke/v2/jobs/28589/"
    "technical-smoke-result.json"
)
TECHNICAL_SMOKE_RESULT_SHA256 = (
    "6d29850cdcc1e044a9381c8a1b2c166ff628a14c0930c49df5ff961f55cb3b52"
)
TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION = TECHNICAL_SMOKE_RESULT.with_name(
    "environment-verification.json"
)
TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION_SHA256 = (
    "886e83ff632021aef51df7a2a5b9a0ed0108df541083eedfa0f56bb686e4cdfe"
)
QUALIFIED_ENVIRONMENT_VERIFIER_SHA256 = (
    "15e85505a790f5f593fae053e9bc8d989866593e3e952ae84c3694500ed1a712"
)
AMENDED_ENVIRONMENT_VERIFIER_SHA256 = (
    "a8b535dc012124a789aea322f6daa3806d915920758e55b20afe19120f66fb4d"
)

PRODUCTION_PROFILE_FILES = (
    FrozenProjectFile(
        Path("configs/models/devstral-small-2507.json"),
        "92fad14e431589cf2c578022f62648f0a63b1fdfd8332a2fdc0d3dbceedf208e",
    ),
    FrozenProjectFile(
        Path("scripts/verify_devstral_environment.py"),
        AMENDED_ENVIRONMENT_VERIFIER_SHA256,
    ),
    FrozenProjectFile(
        Path(
            "src/cmpilot/integrations/miniswe/"
            "devstral_serialization_adapter_runtime.py"
        ),
        "9aaa7877b43ee6ae265f17faa4ee10517ebfb9b8654316e651368fd389632ab4",
    ),
    FrozenProjectFile(
        Path("src/cmpilot/devstral_serialization.py"),
        "d63b15f44baabb4fb4d4fe8dd539b8d16f05b6bc2129eb069e18120a85f3fef6",
    ),
    FrozenProjectFile(
        Path(
            "src/cmpilot/integrations/miniswe/qualification_adapter_runtime.py"
        ),
        "12b7163c23b444f605db65dc7bd705720e61caa4a4a13bfc5359e7830b1ca631",
    ),
)

# The frozen experiment manifests bind the qualified scientific model profile,
# including the verifier that produced smoke job 28589.  The pre-rerun timeout
# amendment changes only the executable runtime verifier.  Keep the scientific
# profile record byte-for-byte stable while verifying the amended runtime file
# through PRODUCTION_PROFILE_FILES and the new project commit.
SCIENTIFIC_PROFILE_IDENTITY_FILES = tuple(
    FrozenProjectFile(
        item.relative_path,
        (
            QUALIFIED_ENVIRONMENT_VERIFIER_SHA256
            if item.relative_path == Path("scripts/verify_devstral_environment.py")
            else item.sha256
        ),
    )
    for item in PRODUCTION_PROFILE_FILES
)

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
    verification_state: str = "TECHNICAL_SMOKE_PASSED"

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


def _load_exact_json(path: Path, *, expected_sha256: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise DevstralProfileError(f"qualified evidence is missing or unsafe: {path}")
    actual = _sha256_file(path)
    if actual != expected_sha256:
        raise DevstralProfileError(
            f"qualified evidence changed: {path}; expected {expected_sha256}, "
            f"found {actual}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevstralProfileError(
            f"qualified evidence is invalid JSON: {path}"
        ) from error
    if not isinstance(value, dict):
        raise DevstralProfileError(f"qualified evidence must be a JSON object: {path}")
    return value


def verify_devstral_production_qualification(project_root: Path) -> tuple[Path, ...]:
    """Verify the frozen profile and already-passed technical qualification.

    This is intentionally a cheap profile gate.  The live environment verifier,
    including the 47 GB runtime-weight hash, is rerun by the model service before
    vLLM is started for an actual production attempt.
    """

    root = Path(project_root).resolve(strict=True)
    verified = [item.verify(root) for item in PRODUCTION_PROFILE_FILES]
    freeze_path = FrozenProjectFile(
        SNAPSHOT_FREEZE, SNAPSHOT_FREEZE_SHA256
    ).verify(root)
    freeze = _load_exact_json(freeze_path, expected_sha256=SNAPSHOT_FREEZE_SHA256)
    snapshot = freeze.get("snapshot")
    serving = freeze.get("serving_profile")
    model = freeze.get("model")
    if (
        freeze.get("schema") != "devstral-snapshot-freeze-v1"
        or freeze.get("freeze_identity_sha256")
        != SNAPSHOT_FREEZE_IDENTITY_SHA256
        or not isinstance(model, dict)
        or model.get("id") != MODEL_ID
        or model.get("revision") != MODEL_REVISION
        or not isinstance(snapshot, dict)
        or snapshot.get("identity_sha256") != SNAPSHOT_IDENTITY_SHA256
        or snapshot.get("model_id") != MODEL_ID
        or snapshot.get("revision") != MODEL_REVISION
        or not isinstance(serving, dict)
        or serving.get("profile_id") != PROFILE_ID
        or serving.get("model_id") != MODEL_ID
        or serving.get("model_revision") != MODEL_REVISION
        or serving.get("served_model_name") != SERVED_MODEL_NAME
    ):
        raise DevstralProfileError("Devstral snapshot freeze identity is inconsistent")
    frozen_server = serving.get("server")
    if not isinstance(frozen_server, dict) or frozen_server != {
        "dtype": SERVER_SETTINGS.dtype,
        "gpu_memory_utilization": SERVER_SETTINGS.gpu_memory_utilization,
        "max_model_length": SERVER_SETTINGS.max_model_length,
        "max_num_sequences": SERVER_SETTINGS.max_num_sequences,
        "quantization": SERVER_SETTINGS.quantization,
        "seed": SERVER_SETTINGS.server_seed,
        "tensor_parallel_size": SERVER_SETTINGS.tensor_parallel_size,
    }:
        raise DevstralProfileError("Devstral serving profile differs from its freeze")

    smoke = _load_exact_json(
        TECHNICAL_SMOKE_RESULT, expected_sha256=TECHNICAL_SMOKE_RESULT_SHA256
    )
    smoke_checks = smoke.get("checks")
    serialization = smoke.get("serialization")
    if (
        smoke.get("schema") != "devstral-technical-smoke-v2"
        or smoke.get("smoke_id") != "devstral-small-2507-technical-smoke-v2"
        or smoke.get("model_id") != MODEL_ID
        or smoke.get("model_revision") != MODEL_REVISION
        or smoke.get("pass") is not True
        or smoke.get("scientific_evidence") is not False
        or not isinstance(smoke_checks, dict)
        or not smoke_checks
        or not all(value is True for value in smoke_checks.values())
        or not isinstance(serialization, dict)
        or serialization.get("response_conversion") is not None
        or serialization.get("tekken_sha256")
        != dict(STAGED_SNAPSHOT_FILE_SHA256)["tekken.json"]
    ):
        raise DevstralProfileError("Devstral technical-smoke evidence is not qualified")

    environment = _load_exact_json(
        TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION,
        expected_sha256=TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION_SHA256,
    )
    environment_checks = environment.get("checks")
    environment_freeze = environment.get("snapshot_freeze")
    runtime_weight = environment.get("runtime_weight")
    if (
        environment.get("production_ready") is not True
        or environment.get("status") != "READY"
        or not isinstance(environment_checks, dict)
        or not environment_checks
        or not all(value is True for value in environment_checks.values())
        or not isinstance(environment_freeze, dict)
        or environment_freeze.get("freeze_sha256") != SNAPSHOT_FREEZE_SHA256
        or environment_freeze.get("snapshot_identity_sha256")
        != SNAPSHOT_IDENTITY_SHA256
        or not isinstance(runtime_weight, dict)
        or runtime_weight.get("size") != EXPECTED_CONSOLIDATED_SIZE
        or runtime_weight.get("sha256") != EXPECTED_CONSOLIDATED_SHA256
    ):
        raise DevstralProfileError("qualified Devstral environment report is not READY")

    for label, executable in (
        ("server", SERVER_PYTHON),
        ("controller", CONTROLLER_PYTHON),
        ("agent", AGENT_PYTHON),
    ):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise DevstralProfileError(
                f"qualified Devstral {label} interpreter is unavailable: {executable}"
            )
        verified.append(executable.resolve(strict=True))
    return (
        *verified,
        freeze_path,
        TECHNICAL_SMOKE_RESULT.resolve(strict=True),
        TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION.resolve(strict=True),
    )


class DevstralProductionModelProfile(ModelProfile):
    """Qualified Devstral identity for the shared final experiment runner."""

    def verify_static_inputs(self, project_root: Path) -> tuple[Path, ...]:
        shared = super().verify_static_inputs(project_root)
        qualified = verify_devstral_production_qualification(project_root)
        return (*shared, *qualified)

    def identity_record(self) -> dict[str, object]:
        record = super().identity_record()
        record["schema"] = "cmpilot-model-profile-v2"
        record["qualification"] = {
            "agent_environment": {
                "environment_id": AGENT_ENVIRONMENT_ID,
                "freeze": str(CANDIDATE_AGENT_FREEZE),
                "freeze_sha256": CANDIDATE_AGENT_FREEZE_SHA256,
                "lock": str(CANDIDATE_AGENT_LOCK),
                "lock_sha256": CANDIDATE_AGENT_LOCK_SHA256,
            },
            "environment_verifier": {
                "qualified_output_path": str(
                    TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION
                ),
                "qualified_output_sha256": (
                    TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION_SHA256
                ),
                "required_production_ready": True,
                "required_status": "READY",
                "script": "scripts/verify_devstral_environment.py",
            },
            "profile_files": [
                {"path": item.relative_path.as_posix(), "sha256": item.sha256}
                for item in SCIENTIFIC_PROFILE_IDENTITY_FILES
            ],
            "snapshot_freeze": {
                "freeze_identity_sha256": SNAPSHOT_FREEZE_IDENTITY_SHA256,
                "path": str(SNAPSHOT_FREEZE),
                "sha256": SNAPSHOT_FREEZE_SHA256,
                "snapshot_identity_sha256": SNAPSHOT_IDENTITY_SHA256,
                "runtime_weight": {
                    "file": "consolidated.safetensors",
                    "sha256": EXPECTED_CONSOLIDATED_SHA256,
                    "size": EXPECTED_CONSOLIDATED_SIZE,
                },
            },
            "technical_smoke": {
                "job_id": TECHNICAL_SMOKE_JOB_ID,
                "result_path": str(TECHNICAL_SMOKE_RESULT),
                "result_sha256": TECHNICAL_SMOKE_RESULT_SHA256,
                "schema": "devstral-technical-smoke-v2",
            },
        }
        return record


def _build_devstral_production_server_argv(port: int) -> tuple[str, ...]:
    return build_devstral_server_argv(port=port)


DEVSTRAL_PRODUCTION_PROFILE = DevstralProductionModelProfile(
    profile_id=PROFILE_ID,
    model_id=MODEL_ID,
    model_revision=MODEL_REVISION,
    model_snapshot=MODEL_SNAPSHOT,
    served_model_name=SERVED_MODEL_NAME,
    environment=RuntimeEnvironmentIdentity(
        environment_id=ENVIRONMENT_ID,
        server_python=SERVER_PYTHON,
        controller_python=CONTROLLER_PYTHON,
        agent_python=AGENT_PYTHON,
        environment_fingerprint=ENVIRONMENT_FINGERPRINT_SHA256,
        environment_content_digest=ENVIRONMENT_CONTENT_DIGEST_SHA256,
        package_versions=CANDIDATE_PACKAGE_VERSIONS,
        offline_environment=OFFLINE_ENVIRONMENT,
    ),
    serialization=SerializationIdentity(
        tokenizer_path=MODEL_SNAPSHOT,
        assets=(("tekken.json", dict(STAGED_SNAPSHOT_FILE_SHA256)["tekken.json"]),),
        serialization_mode="mistral-common-tekken",
        chat_template_source=CHAT_TEMPLATE_SOURCE,
        add_generation_prompt=True,
    ),
    server=SERVER_SETTINGS,
    generation=GENERATION_SETTINGS,
    _server_command_builder=_build_devstral_production_server_argv,
    _server_command_validator=validate_devstral_server_argv,
)


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
    "DEVSTRAL_PRODUCTION_PROFILE",
    "DevstralCandidateProfile",
    "DevstralProductionModelProfile",
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
    "PRODUCTION_PROFILE_FILES",
    "REQUIRED_SNAPSHOT_FILES",
    "SERVER_PYTHON",
    "SERVED_MODEL_NAME",
    "SNAPSHOT_FREEZE",
    "SNAPSHOT_FREEZE_IDENTITY_SHA256",
    "SNAPSHOT_FREEZE_SHA256",
    "SNAPSHOT_IDENTITY_SHA256",
    "TOKENIZER_MODE",
    "STAGED_SNAPSHOT_FILE_SHA256",
    "TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION",
    "TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION_SHA256",
    "TECHNICAL_SMOKE_JOB_ID",
    "TECHNICAL_SMOKE_RESULT",
    "TECHNICAL_SMOKE_RESULT_SHA256",
    "VerifiedDevstralIdentity",
    "build_devstral_server_argv",
    "normalize_package_name",
    "validate_candidate_agent_environment",
    "validate_candidate_environment",
    "validate_devstral_server_argv",
    "verify_devstral_readiness",
    "verify_devstral_production_qualification",
]

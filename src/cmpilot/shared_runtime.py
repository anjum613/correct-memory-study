"""Stage and validate Slurm runtime helpers on explicitly shared storage."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
from typing import Iterable, Sequence

from cmpilot.file_digest import sha256_file


NON_SHARED_RUNTIME_PATH = "NON_SHARED_RUNTIME_PATH"
BATCH_RUNTIME_PATH_VISIBILITY_FAILURE = "BATCH_RUNTIME_PATH_VISIBILITY_FAILURE"
RUNTIME_SOURCE_HASH_MISMATCH = "RUNTIME_SOURCE_HASH_MISMATCH"
MISSING_MANDATORY_EXECUTABLE = "MISSING_MANDATORY_EXECUTABLE"
REQUIRED_FILE_MARKER = "# CMPILOT_REQUIRED_RUNTIME_FILE="
REQUIRED_EXECUTABLE_MARKER = "# CMPILOT_MANDATORY_EXECUTABLE="
DEFAULT_SHARED_ROOTS = (Path("/home/s224049759"),)
_NODE_LOCAL_ROOTS = (Path("/tmp"), Path("/var/tmp"))
_MISSING_PATH = re.compile(r"cannot stat ['\"](?P<path>[^'\"]+)['\"]")


class RuntimePathError(ValueError):
    """A batch runtime file is not provably visible on compute nodes."""


@dataclass(frozen=True)
class StagedRuntimeDriver:
    path: Path
    sha256: str
    source: Path


def _beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_failure(path: object, reason: str) -> RuntimePathError:
    return RuntimePathError(f"{NON_SHARED_RUNTIME_PATH}: {path!s}: {reason}")


def validate_runtime_path(
    raw_path: str | Path,
    *,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
) -> Path:
    """Require an existing readable regular file beneath a configured shared root."""
    raw = str(raw_path)
    if not raw or "$" in raw or "`" in raw or raw.startswith("~"):
        raise _path_failure(raw, "unresolved shell-variable or home-relative path")
    path = Path(raw)
    if not path.is_absolute():
        raise _path_failure(raw, "relative path has no established shared base")
    lexical = Path(os.path.abspath(path))
    if any(_beneath(lexical, root) for root in _NODE_LOCAL_ROOTS):
        raise _path_failure(raw, "node-local temporary storage is not shared")
    normalized_roots: list[Path] = []
    for root in shared_roots:
        if not root.is_absolute():
            raise ValueError(f"shared root must be absolute: {root}")
        normalized_roots.append(Path(os.path.abspath(root)))
    if not any(_beneath(lexical, root) for root in normalized_roots):
        raise _path_failure(raw, "path is outside configured shared roots")
    if not lexical.exists() and not lexical.is_symlink():
        raise _path_failure(raw, "required file does not exist")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as error:
        raise _path_failure(raw, f"cannot resolve required file: {error}") from error
    if not any(_beneath(resolved, root.resolve()) for root in normalized_roots):
        raise _path_failure(raw, "symlink resolves outside configured shared roots")
    information = lexical.stat()
    if not stat.S_ISREG(information.st_mode):
        raise _path_failure(raw, "required runtime path is not a regular file")
    if information.st_mode & 0o444 == 0 or not os.access(lexical, os.R_OK):
        raise _path_failure(raw, "required runtime file is not readable")
    return resolved


def runtime_paths_from_script(script: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in script.splitlines():
        if line.startswith(REQUIRED_FILE_MARKER):
            paths.append(line.removeprefix(REQUIRED_FILE_MARKER))
    return tuple(paths)


def validate_script_runtime_paths(
    script: str,
    *,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
) -> tuple[Path, ...]:
    """Validate every project runtime file declared by a generated script."""
    paths = runtime_paths_from_script(script)
    if not paths:
        raise RuntimePathError(
            f"{NON_SHARED_RUNTIME_PATH}: generated script declares no runtime files"
        )
    return tuple(
        validate_runtime_path(path, shared_roots=shared_roots) for path in paths
    )


def executable_paths_from_script(script: str) -> tuple[str, ...]:
    """Return executable declarations embedded in a generated script."""
    return tuple(
        line.removeprefix(REQUIRED_EXECUTABLE_MARKER)
        for line in script.splitlines()
        if line.startswith(REQUIRED_EXECUTABLE_MARKER)
    )


def validate_script_executables(script: str) -> tuple[Path, ...]:
    """Fail before submission when a declared executable is unavailable."""
    raw_paths = executable_paths_from_script(script)
    if not raw_paths:
        raise RuntimePathError(
            f"{MISSING_MANDATORY_EXECUTABLE}: generated script declares no executables"
        )
    validated: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            raise RuntimePathError(
                f"{MISSING_MANDATORY_EXECUTABLE}: path is not absolute: {raw_path}"
            )
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimePathError(
                f"{MISSING_MANDATORY_EXECUTABLE}: unavailable: {raw_path}"
            )
        validated.append(path.resolve())
    return tuple(validated)


def stage_runtime_driver(
    source: Path,
    pre_submit_directory: Path,
    *,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
    destination_name: str = "guided-backend-cpu-gate.py",
) -> StagedRuntimeDriver:
    """Copy a driver once into a new shared pre-submit directory and make it read-only."""
    source = source.resolve(strict=True)
    if not source.is_file():
        raise ValueError(f"runtime driver source is not a regular file: {source}")
    if pre_submit_directory.exists():
        raise FileExistsError(f"pre-submit directory already exists: {pre_submit_directory}")
    if not pre_submit_directory.is_absolute():
        raise _path_failure(pre_submit_directory, "pre-submit directory is relative")
    lexical_directory = Path(os.path.abspath(pre_submit_directory))
    roots = [Path(os.path.abspath(root)) for root in shared_roots]
    if not any(_beneath(lexical_directory, root) for root in roots):
        raise _path_failure(pre_submit_directory, "pre-submit directory is not shared")
    if any(_beneath(lexical_directory, root) for root in _NODE_LOCAL_ROOTS):
        raise _path_failure(pre_submit_directory, "pre-submit directory is node-local")
    lexical_directory.mkdir(parents=True, exist_ok=False)
    destination = lexical_directory / destination_name
    shutil.copyfile(source, destination)
    destination.chmod(0o444)
    validated = validate_runtime_path(destination, shared_roots=shared_roots)
    return StagedRuntimeDriver(
        path=validated,
        sha256=sha256_file(validated),
        source=source,
    )


def _quoted_assignment(name: str, value: str | Path) -> str:
    return f"{name}={shlex.quote(str(value))}"


def render_cpu_gate_wrapper(
    *,
    driver_path: Path,
    driver_sha256: str,
    artifact_root: Path,
    driver_interpreter: Path,
    driver_arguments: Iterable[str] = (),
    required_runtime_paths: Iterable[Path] = (),
    strict_runtime_inputs: Iterable[StagedRuntimeDriver] = (),
    digest_tool: Path | None = None,
    digest_interpreter: Path = Path(
        "/home/s224049759/environments/cmpilot-conda/bin/python"
    ),
    submitted_script_path: Path | None = None,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
    job_name: str = "guided-backend-shared-path",
) -> str:
    """Render the CPU-only wrapper that verifies and preserves its shared driver."""
    validated_driver = validate_runtime_path(driver_path, shared_roots=shared_roots)
    if digest_tool is None:
        digest_tool = (
            Path(__file__).resolve().parents[2]
            / "scripts"
            / "batch_script_attestation.py"
        )
    validated_digest_tool = validate_runtime_path(
        digest_tool, shared_roots=shared_roots
    )
    validated_requirements = [
        validate_runtime_path(path, shared_roots=shared_roots)
        for path in required_runtime_paths
    ]
    validated_strict_inputs = [
        StagedRuntimeDriver(
            path=validate_runtime_path(reference.path, shared_roots=shared_roots),
            sha256=reference.sha256,
            source=reference.source,
        )
        for reference in strict_runtime_inputs
    ]
    if not re.fullmatch(r"[0-9a-f]{64}", driver_sha256):
        raise ValueError("driver_sha256 must be lowercase SHA-256")
    if any(
        not re.fullmatch(r"[0-9a-f]{64}", item.sha256)
        for item in validated_strict_inputs
    ):
        raise ValueError("strict runtime input hashes must be lowercase SHA-256")
    if not all(
        path.is_absolute()
        for path in (artifact_root, driver_interpreter, digest_interpreter)
    ):
        raise ValueError("artifact root and interpreters must be absolute")
    mandatory_executables = tuple(
        dict.fromkeys(
            (
                Path("/usr/bin/bash"),
                Path("/usr/bin/cp"),
                Path("/usr/bin/hostname"),
                Path("/usr/bin/mkdir"),
                Path("/usr/bin/printf"),
                driver_interpreter,
                digest_interpreter,
            )
        )
    )
    submitted_marker = ""
    submitted_assignment = "SUBMITTED_SCRIPT_PATH=''"
    submitted_copy = ""
    if submitted_script_path is not None:
        submitted_marker = f"{REQUIRED_FILE_MARKER}{submitted_script_path}\n"
        submitted_assignment = _quoted_assignment(
            "SUBMITTED_SCRIPT_PATH", submitted_script_path
        )
        submitted_copy = (
            '/usr/bin/cp -- "$SUBMITTED_SCRIPT_PATH" '
            '"$ARTIFACT_DIR/submitted.sbatch"\n'
        )
    arguments = " ".join(shlex.quote(str(value)) for value in driver_arguments)
    marked_runtime_paths = tuple(
        dict.fromkeys(
            (
                validated_digest_tool,
                *validated_requirements,
                *(reference.path for reference in validated_strict_inputs),
            )
        )
    )
    requirement_markers = "".join(
        f"{REQUIRED_FILE_MARKER}{path}\n" for path in marked_runtime_paths
    )
    executable_markers = "".join(
        f"{REQUIRED_EXECUTABLE_MARKER}{path}\n" for path in mandatory_executables
    )
    executable_array = " ".join(
        shlex.quote(str(path)) for path in mandatory_executables
    )
    strict_path_array = " ".join(
        shlex.quote(str(reference.path)) for reference in validated_strict_inputs
    )
    strict_hash_array = " ".join(
        shlex.quote(reference.sha256) for reference in validated_strict_inputs
    )
    strict_context_array = " ".join(
        shlex.quote(
            "server-command-plan"
            if "server-command" in reference.path.name
            else reference.path.name
        )
        for reference in validated_strict_inputs
    )
    invocation = (
        'exec "$DRIVER_INTERPRETER" "$DRIVER_PATH"'
        + (f" {arguments}" if arguments else "")
        + "\n"
    )
    wrapper = f"""#!/usr/bin/bash
#SBATCH --partition=Virtual
#SBATCH --nodes=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --no-requeue
#SBATCH --job-name={job_name}
#SBATCH --output={artifact_root}/slurm-%j.out
#SBATCH --error={artifact_root}/slurm-%j.err
{REQUIRED_FILE_MARKER}{validated_driver}
{requirement_markers}{submitted_marker}{executable_markers}set -euo pipefail
{_quoted_assignment("DRIVER_PATH", validated_driver)}
EXPECTED_DRIVER_SHA256={driver_sha256}
{_quoted_assignment("DIGEST_TOOL", validated_digest_tool)}
{_quoted_assignment("DIGEST_INTERPRETER", digest_interpreter)}
{_quoted_assignment("ARTIFACT_ROOT", artifact_root)}
{_quoted_assignment("DRIVER_INTERPRETER", driver_interpreter)}
{submitted_assignment}
ARTIFACT_DIR="$ARTIFACT_ROOT/${{SLURM_JOB_ID:?SLURM_JOB_ID is required}}"
MANDATORY_EXECUTABLES=({executable_array})
STRICT_RUNTIME_PATHS=({strict_path_array})
STRICT_RUNTIME_SHA256S=({strict_hash_array})
STRICT_RUNTIME_CONTEXTS=({strict_context_array})
for REQUIRED_EXECUTABLE in "${{MANDATORY_EXECUTABLES[@]}}"; do
    if [[ ! -f "$REQUIRED_EXECUTABLE" || ! -x "$REQUIRED_EXECUTABLE" ]]; then
        /usr/bin/printf '{MISSING_MANDATORY_EXECUTABLE}: %s\\n' \
            "$REQUIRED_EXECUTABLE" >&2
        exit 40
    fi
done
/usr/bin/mkdir -p -- "$ARTIFACT_DIR"

set +e
"$DIGEST_INTERPRETER" "$DIGEST_TOOL" observe --path "$0" \
    --record "$ARTIFACT_DIR/running-script-observation.json" \
    >"$ARTIFACT_DIR/running-script-observation.stdout" \
    2>"$ARTIFACT_DIR/running-script-observation.stderr"
RUNNING_SCRIPT_OBSERVATION_STATUS=$?
set -e
/usr/bin/printf '%s\\n' "$RUNNING_SCRIPT_OBSERVATION_STATUS" \
    >"$ARTIFACT_DIR/running-script-observation.exit"

write_failure() {{
    local label=$1
    /usr/bin/printf '{{"backend_checks_ran":false,"label":"%s"}}\\n' "$label" \
        >"$ARTIFACT_DIR/classification.json"
}}

verify_runtime_input() {{
    local input_path=$1
    local expected_digest=$2
    local context=$3
    local evidence_stem=$4
    local status
    set +e
    "$DIGEST_INTERPRETER" "$DIGEST_TOOL" verify \
        --path "$input_path" \
        --expected "$expected_digest" \
        --context "$context" \
        --record "$ARTIFACT_DIR/${{evidence_stem}}-digest-comparison.json" \
        >"$ARTIFACT_DIR/${{evidence_stem}}.sha256" \
        2>"$ARTIFACT_DIR/${{evidence_stem}}-digest.stderr"
    status=$?
    set -e
    /usr/bin/printf '%s\\n' "$status" \
        >"$ARTIFACT_DIR/${{evidence_stem}}-digest.exit"
    return "$status"
}}

if [[ ! -f "$DRIVER_PATH" || ! -r "$DRIVER_PATH" ]]; then
    write_failure {NON_SHARED_RUNTIME_PATH}
    exit 41
fi
if ! verify_runtime_input \
    "$DRIVER_PATH" "$EXPECTED_DRIVER_SHA256" shared-driver driver; then
    write_failure {RUNTIME_SOURCE_HASH_MISMATCH}
    exit 42
fi

for ((INPUT_INDEX=0; INPUT_INDEX<${{#STRICT_RUNTIME_PATHS[@]}}; INPUT_INDEX++)); do
    INPUT_PATH=${{STRICT_RUNTIME_PATHS[$INPUT_INDEX]}}
    INPUT_SHA256=${{STRICT_RUNTIME_SHA256S[$INPUT_INDEX]}}
    INPUT_CONTEXT=${{STRICT_RUNTIME_CONTEXTS[$INPUT_INDEX]}}
    INPUT_STEM="strict-runtime-input-${{INPUT_INDEX}}"
    if ! verify_runtime_input \
        "$INPUT_PATH" "$INPUT_SHA256" "$INPUT_CONTEXT" "$INPUT_STEM"; then
        write_failure {RUNTIME_SOURCE_HASH_MISMATCH}
        exit 43
    fi
    /usr/bin/cp -- "$INPUT_PATH" "$ARTIFACT_DIR/${{INPUT_STEM}}"
done

/usr/bin/hostname >"$ARTIFACT_DIR/hostname.txt"
/usr/bin/printf '%s\\n' "$DRIVER_PATH" >"$ARTIFACT_DIR/driver-path.txt"
/usr/bin/cp -- "$DRIVER_PATH" "$ARTIFACT_DIR/submitted-driver.sh"
{submitted_copy}export ARTIFACT_DIR
{invocation}"""
    validate_script_executables(wrapper)
    return wrapper


def classify_batch_runtime_failure(
    *, stderr: str, stdout: str, script: str
) -> dict[str, object]:
    """Classify a missing node-local source before backend execution."""
    match = _MISSING_PATH.search(stderr)
    missing_path = match.group("path") if match else None
    backend_checks_ran = "GUIDED_BACKEND_CHECK_STARTED" in stdout
    is_node_local = bool(
        missing_path
        and any(
            _beneath(Path(os.path.abspath(missing_path)), root)
            for root in _NODE_LOCAL_ROOTS
        )
    )
    if is_node_local and missing_path in script and not backend_checks_ran:
        label = BATCH_RUNTIME_PATH_VISIBILITY_FAILURE
    else:
        label = "BATCH_RUNTIME_FAILURE_UNCLASSIFIED"
    return {
        "backend_checks_ran": backend_checks_ran,
        "backend_result": None if not backend_checks_ran else "UNKNOWN",
        "dimensions": {
            "environment_corruption": False,
            "gpu_failure": False,
            "guided_backend_dependency_failure": False,
            "model_failure": False,
            "vllm_failure": False,
        },
        "label": label,
        "missing_path": missing_path,
    }


def write_runtime_manifest(
    path: Path, references: Iterable[StagedRuntimeDriver]
) -> None:
    rows = [
        {"path": str(reference.path), "sha256": reference.sha256}
        for reference in references
    ]
    path.write_text(
        json.dumps(
            {
                "classification_on_failure": NON_SHARED_RUNTIME_PATH,
                "runtime_files": rows,
                "schema": "shared-slurm-runtime-manifest-v1",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

"""Model-neutral identity, resume, and aggregation for the final experiment.

This module deliberately does not select triplet families or a memory design.  It
only accepts a fully frozen manifest and turns that manifest into immutable atomic
run identities.  Runtime code can then use those identities without re-running
selection or deriving seeds at execution time.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .calculator_finalizer import (
    CalculatorFinalizerError,
    initialize_finalizer_state,
    load_finalizer_state,
    validate_total_finalization_artifacts,
)


EXPERIMENT_SCHEMA = "cmpilot-final-experiment-v2"
MATRIX_SCHEMA = "cmpilot-final-run-matrix-v2"
RUN_SCHEMA = "cmpilot-final-run-v2"
RUN_IDENTITY_SCHEMA = "cmpilot-final-run-identity-v2"
CONDITION_IDENTITY_SCHEMA = "cmpilot-final-condition-identity-v1"
RUN_CONTEXT_SCHEMA = "cmpilot-final-run-context-v1"
ATTEMPT_PROVENANCE_SCHEMA = "cmpilot-final-run-attempt-provenance-v1"
AGGREGATION_SCHEMA = "cmpilot-final-experiment-aggregation-v1"

PRODUCTION = "PRODUCTION"
SYNTHETIC_UNIT_TEST = "SYNTHETIC_UNIT_TEST"
FROZEN = "FROZEN"
SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
MANIFEST_PURPOSES = frozenset({PRODUCTION, SYNTHETIC_UNIT_TEST})

NO_MEMORY = "NO_MEMORY"
SOURCE_CORRECT_MEMORY = "SOURCE_CORRECT_MEMORY"
REQUIRED_CONDITIONS = frozenset({NO_MEMORY, SOURCE_CORRECT_MEMORY})
MEMORY_MODES = frozenset({"FIXED_EXTERNAL", "PER_MODEL_GENERATED"})
ATTEMPT_STATES = ("ABSENT", "INTERRUPTED", "COMPLETED")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class FinalExperimentError(ValueError):
    """The frozen experiment, matrix, or result inventory is inconsistent."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the repository's canonical, human-readable JSON representation."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FinalExperimentError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise FinalExperimentError(f"non-finite JSON number is forbidden: {value}")


def _parse_json_object(payload: bytes, *, source: str) -> dict[str, Any]:
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalExperimentError(f"invalid UTF-8 JSON in {source}: {error}") from error
    if not isinstance(value, dict):
        raise FinalExperimentError(f"expected a JSON object in {source}")
    return value


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FinalExperimentError(f"{name} must be an object")
    return value


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinalExperimentError(f"{name} must be a non-empty string")
    return value


def _identifier(value: Any, name: str) -> str:
    value = _nonempty_string(value, name)
    if not _IDENTIFIER.fullmatch(value):
        raise FinalExperimentError(f"{name} is not a portable identifier: {value}")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise FinalExperimentError(
            f"{name} must be exactly 64 lowercase hexadecimal characters"
        )
    return value


def _revision(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        raise FinalExperimentError(
            f"{name} must be an immutable 40-character lowercase revision"
        )
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FinalExperimentError(f"{name} must be a positive integer")
    return value


def _seed(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FinalExperimentError(f"{name} must be a non-negative integer")
    return value


def _nonempty_json(value: Any, name: str) -> None:
    if value is None or value == "" or value == [] or value == {}:
        raise FinalExperimentError(f"{name} must record a value")


def _digest_record(value: Any, name: str) -> Mapping[str, Any]:
    record = _mapping(value, name)
    _sha256(record.get("sha256"), f"{name}.sha256")
    evidence = [item for key, item in record.items() if key != "sha256"]
    if not evidence or all(item in (None, "", [], {}) for item in evidence):
        raise FinalExperimentError(f"{name} must include provenance beside its hash")
    return record


def _manifest_purpose(
    record: Mapping[str, Any], *, allow_synthetic: bool
) -> tuple[str, str]:
    purpose = record.get("purpose")
    if purpose not in MANIFEST_PURPOSES:
        raise FinalExperimentError(
            f"purpose must be one of {sorted(MANIFEST_PURPOSES)}"
        )
    freeze_status = _nonempty_string(record.get("freeze_status"), "freeze_status")
    if purpose == PRODUCTION:
        if freeze_status != FROZEN:
            raise FinalExperimentError(
                "a PRODUCTION manifest must have freeze_status=FROZEN"
            )
    else:
        if freeze_status != SYNTHETIC_ONLY:
            raise FinalExperimentError(
                "a SYNTHETIC_UNIT_TEST manifest must have "
                "freeze_status=SYNTHETIC_ONLY"
            )
        if not allow_synthetic:
            raise FinalExperimentError(
                "SYNTHETIC_UNIT_TEST manifests require an explicit diagnostic flag"
            )
    return str(purpose), freeze_status


def _validate_models(value: Any) -> dict[str, Mapping[str, Any]]:
    models = _mapping(value, "models")
    if not models:
        raise FinalExperimentError("models must contain at least one model profile")
    validated: dict[str, Mapping[str, Any]] = {}
    for key, raw_profile in models.items():
        profile_key = _identifier(key, "model profile key")
        profile = _mapping(raw_profile, f"models.{profile_key}")
        _nonempty_string(profile.get("model_id"), f"models.{profile_key}.model_id")
        _revision(profile.get("revision"), f"models.{profile_key}.revision")
        _nonempty_string(
            profile.get("environment_id"), f"models.{profile_key}.environment_id"
        )
        _sha256(
            profile.get("environment_sha256"),
            f"models.{profile_key}.environment_sha256",
        )
        _sha256(
            profile.get("profile_sha256"), f"models.{profile_key}.profile_sha256"
        )
        _positive_int(
            profile.get("context_limit"), f"models.{profile_key}.context_limit"
        )
        _positive_int(profile.get("step_limit"), f"models.{profile_key}.step_limit")
        generation = _mapping(
            profile.get("generation_parameters"),
            f"models.{profile_key}.generation_parameters",
        )
        if not generation:
            raise FinalExperimentError(
                f"models.{profile_key}.generation_parameters must not be empty"
            )
        generation_sha256 = _sha256(
            profile.get("generation_parameters_sha256"),
            f"models.{profile_key}.generation_parameters_sha256",
        )
        actual_generation_sha256 = sha256_bytes(canonical_json_bytes(generation))
        if generation_sha256 != actual_generation_sha256:
            raise FinalExperimentError(
                f"models.{profile_key}.generation_parameters_sha256 does not "
                "match the recorded generation parameters"
            )
        validated[profile_key] = profile
    return validated


def _validate_memory_record(
    value: Any,
    *,
    name: str,
    family: Mapping[str, Any],
    memory_mode: str,
    model_key: str | None,
    models: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    record = _mapping(value, name)
    source_task = _nonempty_string(record.get("source_task"), f"{name}.source_task")
    source_revision = _revision(
        record.get("source_repository_revision"),
        f"{name}.source_repository_revision",
    )
    if source_task != family["source_task_identity"]:
        raise FinalExperimentError(f"{name} names a different source task")
    if source_revision != family["source_revision"]:
        raise FinalExperimentError(f"{name} names a different source revision")
    _sha256(record.get("content_sha256"), f"{name}.content_sha256")
    _sha256(
        record.get("provenance_manifest_sha256"),
        f"{name}.provenance_manifest_sha256",
    )

    generation_fields = ("generating_model", "model_revision", "generation_seed")
    if memory_mode == "FIXED_EXTERNAL":
        present = [field for field in generation_fields if field in record]
        if present:
            raise FinalExperimentError(
                f"{name} is FIXED_EXTERNAL but has generation fields: {present}"
            )
    else:
        if model_key is None:  # pragma: no cover - guarded by caller
            raise FinalExperimentError(f"{name} is missing its model profile key")
        profile = models[model_key]
        generating_model = _nonempty_string(
            record.get("generating_model"), f"{name}.generating_model"
        )
        if generating_model != profile["model_id"]:
            raise FinalExperimentError(f"{name} generating model does not match profile")
        model_revision = _revision(
            record.get("model_revision"), f"{name}.model_revision"
        )
        if model_revision != profile["revision"]:
            raise FinalExperimentError(f"{name} model revision does not match profile")
        _seed(record.get("generation_seed"), f"{name}.generation_seed")
    return record


def _validate_family(
    value: Any,
    *,
    index: int,
    memory_mode: str,
    memory_conditions: set[str],
    models: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    name = f"families[{index}]"
    family = _mapping(value, name)
    _identifier(family.get("family_id"), f"{name}.family_id")
    _nonempty_string(family.get("repository_identity"), f"{name}.repository_identity")
    _nonempty_string(
        family.get("source_task_identity"), f"{name}.source_task_identity"
    )
    _nonempty_string(
        family.get("target_task_identity"), f"{name}.target_task_identity"
    )
    _revision(family.get("source_revision"), f"{name}.source_revision")
    _revision(family.get("target_revision"), f"{name}.target_revision")
    _nonempty_json(
        family.get("changed_trust_assumption"), f"{name}.changed_trust_assumption"
    )
    _nonempty_string(family.get("transition_type"), f"{name}.transition_type")
    for field in (
        "tptm_provenance",
        "selection_provenance",
        "task_specification",
        "source_functionality_tests",
        "target_functionality_tests",
        "security_witness",
        "task_environment",
    ):
        _digest_record(family.get(field), f"{name}.{field}")

    memories = _mapping(family.get("memories"), f"{name}.memories")
    for condition_key in memories:
        _identifier(condition_key, f"{name}.memories condition")
    unexpected_memory_keys = sorted(
        set(memories) - (memory_conditions | {NO_MEMORY})
    )
    if unexpected_memory_keys:
        raise FinalExperimentError(
            f"{name}.memories contains conditions absent from the manifest: "
            f"{unexpected_memory_keys}"
        )
    if NO_MEMORY in memories and memories[NO_MEMORY] is not None:
        raise FinalExperimentError(f"{name}.memories must not inject NO_MEMORY")
    actual_conditions = {key for key, item in memories.items() if item is not None}
    if actual_conditions != memory_conditions:
        raise FinalExperimentError(
            f"{name}.memories conditions differ: "
            f"expected={sorted(memory_conditions)}, actual={sorted(actual_conditions)}"
        )

    for condition in sorted(memory_conditions):
        raw_memory = memories[condition]
        memory_name = f"{name}.memories.{condition}"
        if memory_mode == "FIXED_EXTERNAL":
            _validate_memory_record(
                raw_memory,
                name=memory_name,
                family=family,
                memory_mode=memory_mode,
                model_key=None,
                models=models,
            )
        else:
            per_model = _mapping(raw_memory, memory_name)
            if set(per_model) != set(models):
                raise FinalExperimentError(
                    f"{memory_name} must contain exactly the evaluated model keys"
                )
            for model_key in sorted(models):
                _validate_memory_record(
                    per_model[model_key],
                    name=f"{memory_name}.{model_key}",
                    family=family,
                    memory_mode=memory_mode,
                    model_key=model_key,
                    models=models,
                )
    return family


def _validate_condition_definitions(
    value: Any, *, conditions: Sequence[str]
) -> dict[str, Mapping[str, Any]]:
    definitions = _mapping(value, "condition_definitions")
    if set(definitions) != set(conditions):
        raise FinalExperimentError(
            "condition_definitions must contain exactly the declared conditions"
        )
    validated: dict[str, Mapping[str, Any]] = {}
    for condition in conditions:
        name = f"condition_definitions.{condition}"
        definition = _digest_record(definitions[condition], name)
        _nonempty_string(definition.get("treatment_type"), f"{name}.treatment_type")
        requires_memory = definition.get("requires_memory")
        if not isinstance(requires_memory, bool):
            raise FinalExperimentError(f"{name}.requires_memory must be Boolean")
        validated[condition] = definition
    if validated[NO_MEMORY]["requires_memory"] is not False:
        raise FinalExperimentError("NO_MEMORY must not require memory")
    if validated[SOURCE_CORRECT_MEMORY]["requires_memory"] is not True:
        raise FinalExperimentError("SOURCE_CORRECT_MEMORY must require memory")
    return validated


def validate_experiment_manifest(
    value: Any, *, allow_synthetic: bool = False
) -> dict[str, Any]:
    """Validate and return an independent JSON copy of a frozen experiment."""

    record = _mapping(value, "experiment manifest")
    if record.get("schema") != EXPERIMENT_SCHEMA:
        raise FinalExperimentError(f"unsupported experiment schema: {record.get('schema')}")
    _manifest_purpose(record, allow_synthetic=allow_synthetic)
    _nonempty_string(record.get("protocol_version"), "protocol_version")
    evaluator = _digest_record(record.get("evaluator"), "evaluator")
    _nonempty_string(evaluator.get("version"), "evaluator.version")
    finalizer = _digest_record(record.get("finalizer"), "finalizer")
    _nonempty_string(finalizer.get("version"), "finalizer.version")
    memory_mode = record.get("memory_mode")
    if memory_mode not in MEMORY_MODES:
        raise FinalExperimentError(
            f"memory_mode must be one of {sorted(MEMORY_MODES)}"
        )

    raw_conditions = record.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise FinalExperimentError("conditions must be a non-empty list")
    conditions = [_identifier(item, "condition") for item in raw_conditions]
    if len(set(conditions)) != len(conditions):
        raise FinalExperimentError("conditions must be unique")
    missing_conditions = sorted(REQUIRED_CONDITIONS - set(conditions))
    if missing_conditions:
        raise FinalExperimentError(
            f"required conditions are absent: {missing_conditions}"
        )
    condition_definitions = _validate_condition_definitions(
        record.get("condition_definitions"), conditions=conditions
    )

    repetitions = _positive_int(record.get("repetitions"), "repetitions")
    raw_seeds = record.get("seeds")
    if not isinstance(raw_seeds, list):
        raise FinalExperimentError("seeds must be an exact JSON list")
    seeds = [_seed(item, f"seeds[{index}]") for index, item in enumerate(raw_seeds)]
    if len(seeds) != repetitions:
        raise FinalExperimentError("seeds must contain exactly one seed per repetition")
    if len(set(seeds)) != len(seeds):
        raise FinalExperimentError("repetition seeds must be unique")

    models = _validate_models(record.get("models"))
    families = record.get("families")
    if not isinstance(families, list) or len(families) != 6:
        raise FinalExperimentError("families must contain exactly six records")
    memory_conditions = {
        condition
        for condition, definition in condition_definitions.items()
        if definition["requires_memory"] is True
    }
    validated_families = [
        _validate_family(
            family,
            index=index,
            memory_mode=memory_mode,
            memory_conditions=memory_conditions,
            models=models,
        )
        for index, family in enumerate(families)
    ]
    family_ids = [str(family["family_id"]) for family in validated_families]
    if len(set(family_ids)) != 6:
        raise FinalExperimentError("the six family IDs must be unique")

    # JSON round-tripping both detaches the result and rejects non-JSON Python values.
    try:
        detached = json.loads(canonical_json_bytes(record))
    except (TypeError, ValueError) as error:
        raise FinalExperimentError(f"manifest is not pure JSON: {error}") from error
    return detached


def load_experiment_manifest(
    path: Path,
    *,
    expected_sha256: str | None = None,
    allow_synthetic: bool = False,
) -> tuple[dict[str, Any], str]:
    """Load a canonical frozen manifest and return it with its exact file hash."""

    path = Path(path)
    if not path.is_file():
        raise FinalExperimentError(f"experiment manifest is not a regular file: {path}")
    payload = path.read_bytes()
    digest = sha256_bytes(payload)
    if expected_sha256 is not None and digest != _sha256(
        expected_sha256, "expected manifest SHA-256"
    ):
        raise FinalExperimentError(
            f"experiment manifest hash mismatch: expected={expected_sha256}, actual={digest}"
        )
    record = _parse_json_object(payload, source=str(path))
    if payload != canonical_json_bytes(record):
        raise FinalExperimentError(f"experiment manifest is not canonical JSON: {path}")
    return validate_experiment_manifest(
        record, allow_synthetic=allow_synthetic
    ), digest


def _memory_for_run(
    family: Mapping[str, Any],
    *,
    condition: str,
    model_key: str,
    memory_mode: str,
) -> Mapping[str, Any] | None:
    if condition not in family["memories"]:
        return None
    memory = family["memories"][condition]
    if memory_mode == "PER_MODEL_GENERATED":
        memory = memory[model_key]
    return _mapping(memory, "run memory")


def _condition_identity_record(
    *,
    condition: str,
    condition_definition_sha256: str,
    condition_requires_memory: bool,
    memory_mode: str,
    memory: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema": CONDITION_IDENTITY_SCHEMA,
        "condition": condition,
        "condition_definition_sha256": condition_definition_sha256,
        "condition_requires_memory": condition_requires_memory,
        "memory_mode": memory_mode,
        "memory": None if memory is None else dict(memory),
    }


def _run_identity(
    experiment: Mapping[str, Any],
    family: Mapping[str, Any],
    *,
    experiment_manifest_sha256: str,
    condition: str,
    model_key: str,
    repetition: int,
    seed: int,
) -> dict[str, Any]:
    profile = experiment["models"][model_key]
    condition_definition = experiment["condition_definitions"][condition]
    memory = _memory_for_run(
        family,
        condition=condition,
        model_key=model_key,
        memory_mode=experiment["memory_mode"],
    )
    family_manifest_sha256 = sha256_bytes(canonical_json_bytes(family))
    memory_record_sha256 = (
        None if memory is None else sha256_bytes(canonical_json_bytes(memory))
    )
    condition_record_sha256 = sha256_bytes(
        canonical_json_bytes(
            _condition_identity_record(
                condition=condition,
                condition_definition_sha256=condition_definition["sha256"],
                condition_requires_memory=condition_definition["requires_memory"],
                memory_mode=experiment["memory_mode"],
                memory=memory,
            )
        )
    )
    identity = {
        "schema": RUN_IDENTITY_SCHEMA,
        "experiment_manifest_sha256": experiment_manifest_sha256,
        "experiment_purpose": experiment["purpose"],
        "manifest_freeze_status": experiment["freeze_status"],
        "protocol_version": experiment["protocol_version"],
        "family_id": family["family_id"],
        "family_manifest_sha256": family_manifest_sha256,
        "repository_identity": family["repository_identity"],
        "source_task_identity": family["source_task_identity"],
        "target_task_identity": family["target_task_identity"],
        "transition_type": family["transition_type"],
        "tptm_provenance_sha256": family["tptm_provenance"]["sha256"],
        "task_specification_sha256": family["task_specification"]["sha256"],
        "condition": condition,
        "condition_definition_sha256": condition_definition["sha256"],
        "condition_requires_memory": condition_definition["requires_memory"],
        "condition_record_sha256": condition_record_sha256,
        "memory_mode": experiment["memory_mode"],
        "model_profile": model_key,
        "model_id": profile["model_id"],
        "model_revision": profile["revision"],
        "environment_id": profile["environment_id"],
        "environment_sha256": profile["environment_sha256"],
        "model_profile_sha256": profile["profile_sha256"],
        "context_limit": profile["context_limit"],
        "step_limit": profile["step_limit"],
        "generation_parameters_sha256": profile["generation_parameters_sha256"],
        "evaluator_version": experiment["evaluator"]["version"],
        "evaluator_sha256": experiment["evaluator"]["sha256"],
        "finalizer_version": experiment["finalizer"]["version"],
        "finalizer_sha256": experiment["finalizer"]["sha256"],
        "source_revision": family["source_revision"],
        "target_revision": family["target_revision"],
        "repetition": repetition,
        "seed": seed,
        "source_functionality_tests_sha256": family["source_functionality_tests"][
            "sha256"
        ],
        "target_functionality_tests_sha256": family["target_functionality_tests"][
            "sha256"
        ],
        "security_witness_sha256": family["security_witness"]["sha256"],
        "task_environment_sha256": family["task_environment"]["sha256"],
        "memory_content_sha256": None if memory is None else memory["content_sha256"],
        "memory_provenance_manifest_sha256": (
            None if memory is None else memory["provenance_manifest_sha256"]
        ),
        "memory_record_sha256": memory_record_sha256,
        "memory_generating_model": (
            None if memory is None else memory.get("generating_model")
        ),
        "memory_model_revision": (
            None if memory is None else memory.get("model_revision")
        ),
        "memory_generation_seed": (
            None if memory is None else memory.get("generation_seed")
        ),
    }
    return identity


def _run_from_identity(
    identity: Mapping[str, Any],
    *,
    memory: Mapping[str, Any] | None,
) -> dict[str, Any]:
    identity_sha256 = sha256_bytes(canonical_json_bytes(identity))
    return {
        "schema": RUN_SCHEMA,
        "run_id": f"run-{identity_sha256}",
        "identity_sha256": identity_sha256,
        "memory": None if memory is None else dict(memory),
        **{key: value for key, value in identity.items() if key != "schema"},
    }


def build_run_matrix(
    value: Any,
    *,
    experiment_manifest_sha256: str | None = None,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Generate the complete deterministic matrix from a validated freeze."""

    experiment = validate_experiment_manifest(
        value, allow_synthetic=allow_synthetic
    )
    actual_manifest_sha256 = sha256_bytes(canonical_json_bytes(experiment))
    if experiment_manifest_sha256 is not None:
        supplied_manifest_sha256 = _sha256(
            experiment_manifest_sha256, "experiment_manifest_sha256"
        )
        if supplied_manifest_sha256 != actual_manifest_sha256:
            raise FinalExperimentError(
                "experiment_manifest_sha256 does not match the canonical manifest: "
                f"expected={actual_manifest_sha256}, "
                f"actual={supplied_manifest_sha256}"
            )
    manifest_sha256 = actual_manifest_sha256
    families = sorted(experiment["families"], key=lambda item: item["family_id"])
    conditions = sorted(experiment["conditions"])
    model_keys = sorted(experiment["models"])
    runs: list[dict[str, Any]] = []
    for family in families:
        for condition in conditions:
            for repetition_index, seed in enumerate(experiment["seeds"], start=1):
                for model_key in model_keys:
                    memory = _memory_for_run(
                        family,
                        condition=condition,
                        model_key=model_key,
                        memory_mode=experiment["memory_mode"],
                    )
                    identity = _run_identity(
                        experiment,
                        family,
                        experiment_manifest_sha256=manifest_sha256,
                        condition=condition,
                        model_key=model_key,
                        repetition=repetition_index,
                        seed=seed,
                    )
                    runs.append(
                        _run_from_identity(
                            identity,
                            memory=memory,
                        )
                    )
    run_ids = [run["run_id"] for run in runs]
    matrix = {
        "schema": MATRIX_SCHEMA,
        "purpose": experiment["purpose"],
        "freeze_status": experiment["freeze_status"],
        "protocol_version": experiment["protocol_version"],
        "experiment_manifest_sha256": manifest_sha256,
        "memory_mode": experiment["memory_mode"],
        "dimensions": {
            "families": [family["family_id"] for family in families],
            "conditions": conditions,
            "condition_definitions": {
                condition: {
                    "requires_memory": experiment["condition_definitions"][condition][
                        "requires_memory"
                    ],
                    "sha256": experiment["condition_definitions"][condition]["sha256"],
                }
                for condition in conditions
            },
            "models": model_keys,
            "repetitions": experiment["repetitions"],
            "seeds": list(experiment["seeds"]),
        },
        "run_count": len(runs),
        "run_ids_sha256": sha256_bytes(canonical_json_bytes(run_ids)),
        "runs": runs,
    }
    return validate_run_matrix(matrix)


def _identity_from_run(run: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "experiment_manifest_sha256",
        "experiment_purpose",
        "manifest_freeze_status",
        "protocol_version",
        "family_id",
        "family_manifest_sha256",
        "repository_identity",
        "source_task_identity",
        "target_task_identity",
        "transition_type",
        "tptm_provenance_sha256",
        "task_specification_sha256",
        "condition",
        "condition_definition_sha256",
        "condition_requires_memory",
        "condition_record_sha256",
        "memory_mode",
        "model_profile",
        "model_id",
        "model_revision",
        "environment_id",
        "environment_sha256",
        "model_profile_sha256",
        "context_limit",
        "step_limit",
        "generation_parameters_sha256",
        "evaluator_version",
        "evaluator_sha256",
        "finalizer_version",
        "finalizer_sha256",
        "source_revision",
        "target_revision",
        "repetition",
        "seed",
        "source_functionality_tests_sha256",
        "target_functionality_tests_sha256",
        "security_witness_sha256",
        "task_environment_sha256",
        "memory_content_sha256",
        "memory_provenance_manifest_sha256",
        "memory_record_sha256",
        "memory_generating_model",
        "memory_model_revision",
        "memory_generation_seed",
    )
    missing = [key for key in keys if key not in run]
    if missing:
        raise FinalExperimentError(f"run record is missing identity fields: {missing}")
    return {"schema": RUN_IDENTITY_SCHEMA, **{key: run[key] for key in keys}}


def _sorted_identifier_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise FinalExperimentError(f"{name} must be a non-empty list")
    items = [_identifier(item, f"{name}[{index}]") for index, item in enumerate(value)]
    if len(set(items)) != len(items):
        raise FinalExperimentError(f"{name} must contain unique identifiers")
    if items != sorted(items):
        raise FinalExperimentError(f"{name} must use canonical sorted order")
    return items


def _validate_run_memory(run: Mapping[str, Any], *, name: str) -> None:
    condition = _identifier(run.get("condition"), f"{name}.condition")
    memory_mode = run.get("memory_mode")
    if memory_mode not in MEMORY_MODES:
        raise FinalExperimentError(
            f"{name}.memory_mode must be one of {sorted(MEMORY_MODES)}"
        )
    memory = run.get("memory")
    condition_definition_sha256 = _sha256(
        run.get("condition_definition_sha256"),
        f"{name}.condition_definition_sha256",
    )
    condition_requires_memory = run.get("condition_requires_memory")
    if not isinstance(condition_requires_memory, bool):
        raise FinalExperimentError(
            f"{name}.condition_requires_memory must be Boolean"
        )
    memory_identity_fields = (
        "memory_content_sha256",
        "memory_provenance_manifest_sha256",
        "memory_record_sha256",
        "memory_generating_model",
        "memory_model_revision",
        "memory_generation_seed",
    )
    if not condition_requires_memory:
        if memory is not None or any(
            run.get(field) is not None for field in memory_identity_fields
        ):
            raise FinalExperimentError(f"{name} injects memory under NO_MEMORY")
        condition_record = _condition_identity_record(
            condition=condition,
            condition_definition_sha256=condition_definition_sha256,
            condition_requires_memory=False,
            memory_mode=str(memory_mode),
            memory=None,
        )
    else:
        memory_record = _mapping(memory, f"{name}.memory")
        content_sha256 = _sha256(
            memory_record.get("content_sha256"), f"{name}.memory.content_sha256"
        )
        provenance_sha256 = _sha256(
            memory_record.get("provenance_manifest_sha256"),
            f"{name}.memory.provenance_manifest_sha256",
        )
        if run.get("memory_content_sha256") != content_sha256:
            raise FinalExperimentError(f"{name} memory content hash changed")
        if run.get("memory_provenance_manifest_sha256") != provenance_sha256:
            raise FinalExperimentError(f"{name} memory provenance hash changed")
        if memory_record.get("source_task") != run.get("source_task_identity"):
            raise FinalExperimentError(f"{name} memory names a different source task")
        if memory_record.get("source_repository_revision") != run.get("source_revision"):
            raise FinalExperimentError(
                f"{name} memory names a different source revision"
            )
        actual_memory_sha256 = sha256_bytes(canonical_json_bytes(memory_record))
        if run.get("memory_record_sha256") != actual_memory_sha256:
            raise FinalExperimentError(f"{name} memory record hash changed")
        generation_fields = (
            "generating_model",
            "model_revision",
            "generation_seed",
        )
        if memory_mode == "FIXED_EXTERNAL":
            if any(field in memory_record for field in generation_fields) or any(
                run.get(field) is not None
                for field in (
                    "memory_generating_model",
                    "memory_model_revision",
                    "memory_generation_seed",
                )
            ):
                raise FinalExperimentError(
                    f"{name} FIXED_EXTERNAL memory has model-generation provenance"
                )
        else:
            generating_model = _nonempty_string(
                memory_record.get("generating_model"),
                f"{name}.memory.generating_model",
            )
            model_revision = _revision(
                memory_record.get("model_revision"),
                f"{name}.memory.model_revision",
            )
            generation_seed = _seed(
                memory_record.get("generation_seed"),
                f"{name}.memory.generation_seed",
            )
            if (
                run.get("memory_generating_model") != generating_model
                or run.get("memory_model_revision") != model_revision
                or run.get("memory_generation_seed") != generation_seed
            ):
                raise FinalExperimentError(
                    f"{name} memory generation provenance changed"
                )
        condition_record = _condition_identity_record(
            condition=condition,
            condition_definition_sha256=condition_definition_sha256,
            condition_requires_memory=True,
            memory_mode=str(memory_mode),
            memory=memory_record,
        )
    expected_condition_sha256 = sha256_bytes(canonical_json_bytes(condition_record))
    if run.get("condition_record_sha256") != expected_condition_sha256:
        raise FinalExperimentError(f"{name} condition record hash changed")


def _validate_atomic_run_record(
    value: Any, *, name: str = "run"
) -> tuple[Mapping[str, Any], str]:
    run = _mapping(value, name)
    if run.get("schema") != RUN_SCHEMA:
        raise FinalExperimentError(f"{name} has an unsupported schema")
    purpose = run.get("experiment_purpose")
    freeze_status = run.get("manifest_freeze_status")
    if purpose not in MANIFEST_PURPOSES:
        raise FinalExperimentError(f"{name} has an invalid experiment purpose")
    if (purpose == PRODUCTION and freeze_status != FROZEN) or (
        purpose == SYNTHETIC_UNIT_TEST and freeze_status != SYNTHETIC_ONLY
    ):
        raise FinalExperimentError(f"{name} has an invalid manifest freeze status")
    _sha256(run.get("experiment_manifest_sha256"), f"{name}.experiment_manifest_sha256")
    _nonempty_string(run.get("protocol_version"), f"{name}.protocol_version")
    for field in ("family_id", "condition", "model_profile"):
        _identifier(run.get(field), f"{name}.{field}")
    for field in (
        "repository_identity",
        "source_task_identity",
        "target_task_identity",
        "transition_type",
        "model_id",
        "environment_id",
        "evaluator_version",
        "finalizer_version",
    ):
        _nonempty_string(run.get(field), f"{name}.{field}")
    for field in (
        "family_manifest_sha256",
        "tptm_provenance_sha256",
        "task_specification_sha256",
        "condition_record_sha256",
        "condition_definition_sha256",
        "environment_sha256",
        "model_profile_sha256",
        "generation_parameters_sha256",
        "evaluator_sha256",
        "finalizer_sha256",
        "source_functionality_tests_sha256",
        "target_functionality_tests_sha256",
        "security_witness_sha256",
        "task_environment_sha256",
    ):
        _sha256(run.get(field), f"{name}.{field}")
    for field in ("model_revision", "source_revision", "target_revision"):
        _revision(run.get(field), f"{name}.{field}")
    if not isinstance(run.get("condition_requires_memory"), bool):
        raise FinalExperimentError(f"{name}.condition_requires_memory must be Boolean")
    _positive_int(run.get("context_limit"), f"{name}.context_limit")
    _positive_int(run.get("step_limit"), f"{name}.step_limit")
    _positive_int(run.get("repetition"), f"{name}.repetition")
    _seed(run.get("seed"), f"{name}.seed")
    _validate_run_memory(run, name=name)
    identity = _identity_from_run(run)
    identity_sha256 = sha256_bytes(canonical_json_bytes(identity))
    if run.get("identity_sha256") != identity_sha256:
        raise FinalExperimentError(f"{name} identity hash changed")
    expected_id = f"run-{identity_sha256}"
    if run.get("run_id") != expected_id:
        raise FinalExperimentError(f"{name} run ID changed")
    return run, expected_id


def validate_run_matrix(value: Any) -> dict[str, Any]:
    record = _mapping(value, "run matrix")
    if record.get("schema") != MATRIX_SCHEMA:
        raise FinalExperimentError(f"unsupported run matrix schema: {record.get('schema')}")
    purpose, freeze_status = _manifest_purpose(record, allow_synthetic=True)
    protocol_version = _nonempty_string(
        record.get("protocol_version"), "protocol_version"
    )
    experiment_sha256 = _sha256(
        record.get("experiment_manifest_sha256"), "experiment_manifest_sha256"
    )
    memory_mode = record.get("memory_mode")
    if memory_mode not in MEMORY_MODES:
        raise FinalExperimentError(
            f"memory_mode must be one of {sorted(MEMORY_MODES)}"
        )
    dimensions = _mapping(record.get("dimensions"), "dimensions")
    families = _sorted_identifier_list(dimensions.get("families"), "dimensions.families")
    if len(families) != 6:
        raise FinalExperimentError("matrix dimensions must contain exactly six families")
    conditions = _sorted_identifier_list(
        dimensions.get("conditions"), "dimensions.conditions"
    )
    missing_conditions = sorted(REQUIRED_CONDITIONS - set(conditions))
    if missing_conditions:
        raise FinalExperimentError(
            f"matrix dimensions omit required conditions: {missing_conditions}"
        )
    raw_condition_definitions = _mapping(
        dimensions.get("condition_definitions"), "dimensions.condition_definitions"
    )
    if set(raw_condition_definitions) != set(conditions):
        raise FinalExperimentError(
            "matrix condition definitions differ from its condition dimension"
        )
    condition_dimensions: dict[str, tuple[str, bool]] = {}
    for condition in conditions:
        definition = _mapping(
            raw_condition_definitions[condition],
            f"dimensions.condition_definitions.{condition}",
        )
        digest = _sha256(
            definition.get("sha256"),
            f"dimensions.condition_definitions.{condition}.sha256",
        )
        requires_memory = definition.get("requires_memory")
        if not isinstance(requires_memory, bool):
            raise FinalExperimentError(
                f"dimensions.condition_definitions.{condition}.requires_memory "
                "must be Boolean"
            )
        if set(definition) != {"requires_memory", "sha256"}:
            raise FinalExperimentError(
                f"dimensions.condition_definitions.{condition} has unexpected fields"
            )
        condition_dimensions[condition] = (digest, requires_memory)
    if condition_dimensions[NO_MEMORY][1] is not False:
        raise FinalExperimentError("matrix NO_MEMORY must not require memory")
    if condition_dimensions[SOURCE_CORRECT_MEMORY][1] is not True:
        raise FinalExperimentError(
            "matrix SOURCE_CORRECT_MEMORY must require memory"
        )
    models = _sorted_identifier_list(dimensions.get("models"), "dimensions.models")
    repetitions = _positive_int(
        dimensions.get("repetitions"), "dimensions.repetitions"
    )
    raw_seeds = dimensions.get("seeds")
    if not isinstance(raw_seeds, list):
        raise FinalExperimentError("dimensions.seeds must be an exact JSON list")
    seeds = [
        _seed(item, f"dimensions.seeds[{index}]")
        for index, item in enumerate(raw_seeds)
    ]
    if len(seeds) != repetitions:
        raise FinalExperimentError(
            "matrix dimensions must contain one seed per repetition"
        )
    if len(set(seeds)) != len(seeds):
        raise FinalExperimentError("matrix repetition seeds must be unique")
    expected_coordinates = [
        (family, condition, repetition, seed, model)
        for family in families
        for condition in conditions
        for repetition, seed in enumerate(seeds, start=1)
        for model in models
    ]
    runs = record.get("runs")
    if not isinstance(runs, list):
        raise FinalExperimentError("run matrix runs must be a list")
    run_count = _positive_int(record.get("run_count"), "run_count")
    if run_count != len(runs):
        raise FinalExperimentError("run_count does not match the run inventory")
    if len(runs) != len(expected_coordinates):
        raise FinalExperimentError(
            "run inventory is not the complete Cartesian product of its dimensions"
        )
    run_ids: list[str] = []
    for index, (raw_run, expected_coordinate) in enumerate(
        zip(runs, expected_coordinates, strict=True)
    ):
        name = f"runs[{index}]"
        run, expected_id = _validate_atomic_run_record(raw_run, name=name)
        if run.get("experiment_manifest_sha256") != experiment_sha256:
            raise FinalExperimentError(f"{name} names a different experiment")
        if run.get("experiment_purpose") != purpose:
            raise FinalExperimentError(f"{name} names a different experiment purpose")
        if run.get("manifest_freeze_status") != freeze_status:
            raise FinalExperimentError(f"{name} names a different freeze status")
        if run.get("protocol_version") != protocol_version:
            raise FinalExperimentError(f"{name} names a different protocol")
        if run.get("memory_mode") != memory_mode:
            raise FinalExperimentError(f"{name} names a different memory mode")
        run_condition = str(run.get("condition"))
        if run_condition not in condition_dimensions:
            raise FinalExperimentError(f"{name} names an undeclared condition")
        expected_condition_identity = condition_dimensions[run_condition]
        if (
            run.get("condition_definition_sha256"),
            run.get("condition_requires_memory"),
        ) != expected_condition_identity:
            raise FinalExperimentError(f"{name} names a different condition definition")
        coordinate = (
            run.get("family_id"),
            run.get("condition"),
            run.get("repetition"),
            run.get("seed"),
            run.get("model_profile"),
        )
        if coordinate != expected_coordinate:
            raise FinalExperimentError(
                f"{name} violates canonical Cartesian ordering or seed assignment: "
                f"expected={expected_coordinate}, actual={coordinate}"
            )
        run_ids.append(expected_id)
    if len(set(run_ids)) != len(run_ids):
        raise FinalExperimentError("run matrix contains duplicate atomic run IDs")
    expected_inventory_hash = sha256_bytes(canonical_json_bytes(run_ids))
    if record.get("run_ids_sha256") != expected_inventory_hash:
        raise FinalExperimentError("run ID inventory hash changed")
    try:
        return json.loads(canonical_json_bytes(record))
    except (TypeError, ValueError) as error:
        raise FinalExperimentError(f"run matrix is not pure JSON: {error}") from error


def load_run_matrix(
    path: Path, *, expected_sha256: str | None = None
) -> tuple[dict[str, Any], str]:
    path = Path(path)
    if not path.is_file():
        raise FinalExperimentError(f"run matrix is not a regular file: {path}")
    payload = path.read_bytes()
    digest = sha256_bytes(payload)
    if expected_sha256 is not None and digest != _sha256(
        expected_sha256, "expected matrix SHA-256"
    ):
        raise FinalExperimentError(
            f"run matrix hash mismatch: expected={expected_sha256}, actual={digest}"
        )
    record = _parse_json_object(payload, source=str(path))
    if payload != canonical_json_bytes(record):
        raise FinalExperimentError(f"run matrix is not canonical JSON: {path}")
    return validate_run_matrix(record), digest


def validate_run_matrix_against_manifest(
    matrix: Any,
    experiment_manifest: Any,
    *,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Require a matrix to be the exact canonical expansion of its manifest."""

    actual = validate_run_matrix(matrix)
    expected = build_run_matrix(
        experiment_manifest, allow_synthetic=allow_synthetic
    )
    if actual != expected:
        raise FinalExperimentError(
            "run matrix is not the exact expansion of the supplied experiment manifest"
        )
    return actual


def resolve_final_run_context(
    experiment_manifest: Any,
    run: Any,
    *,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Resolve one shared scientific-run context without executing a workflow.

    The returned treatment and family records belong to the shared runner.  A
    model adapter receives only the separately returned model profile record.
    """

    experiment = validate_experiment_manifest(
        experiment_manifest, allow_synthetic=allow_synthetic
    )
    matrix = build_run_matrix(experiment, allow_synthetic=allow_synthetic)
    supplied_run = _mapping(run, "run")
    run_id = _nonempty_string(supplied_run.get("run_id"), "run.run_id")
    matches = [item for item in matrix["runs"] if item["run_id"] == run_id]
    if len(matches) != 1 or matches[0] != supplied_run:
        raise FinalExperimentError(
            "run is not the exact atomic record generated by the supplied manifest"
        )
    resolved_run = matches[0]
    family = next(
        item
        for item in experiment["families"]
        if item["family_id"] == resolved_run["family_id"]
    )
    model_profile = experiment["models"][resolved_run["model_profile"]]
    context = {
        "schema": RUN_CONTEXT_SCHEMA,
        "experiment_manifest_sha256": matrix["experiment_manifest_sha256"],
        "family_manifest": family,
        "condition": resolved_run["condition"],
        "treatment": {
            "condition": resolved_run["condition"],
            "condition_definition": experiment["condition_definitions"][
                resolved_run["condition"]
            ],
            "memory": resolved_run["memory"],
        },
        "model_profile_key": resolved_run["model_profile"],
        "model_profile": model_profile,
        "seed": resolved_run["seed"],
        "repetition": resolved_run["repetition"],
        "run_identity": _identity_from_run(resolved_run),
        "run": resolved_run,
    }
    return json.loads(canonical_json_bytes(context))


def write_new_canonical_json(path: Path, value: Any) -> str:
    """Create a canonical JSON artifact exactly once and return its SHA-256."""

    path = Path(path)
    payload = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as error:
        raise FinalExperimentError(f"refusing to overwrite existing artifact: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return sha256_bytes(payload)


def reserve_run_attempt(
    run: Any,
    output_root: Path,
    *,
    slurm_job_id: str,
    attempt_id: str | None = None,
) -> Path:
    """Atomically reserve one immutable Slurm attempt for an incomplete run."""

    run, _ = _validate_atomic_run_record(run)
    job_id = _identifier(slurm_job_id, "slurm_job_id")
    default_attempt_id = f"slurm-{job_id}"
    if attempt_id is None:
        attempt_id = default_attempt_id
    else:
        attempt_id = _identifier(attempt_id, "attempt_id")
        if attempt_id != default_attempt_id and not attempt_id.startswith(
            f"{default_attempt_id}-"
        ):
            raise FinalExperimentError(
                "attempt_id must equal slurm-<job_id> or begin with "
                "slurm-<job_id>-"
            )
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    if output_root.is_symlink() or not output_root.is_dir():
        raise FinalExperimentError(f"output root is not a real directory: {output_root}")
    initial_status = classify_run_attempts(run, output_root)
    if not initial_status["submission_allowed"]:
        raise FinalExperimentError(
            f"refusing to rerun completed atomic run: {run['run_id']}"
        )
    run_directory = output_root / str(run["run_id"])
    run_directory.mkdir(mode=0o755, exist_ok=True)
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise FinalExperimentError(
            f"run artifact path is not a real directory: {run_directory}"
        )
    lock_path = run_directory / ".attempt-reservation.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "rb+") as lock_stream:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX)
        status = classify_run_attempts(run, output_root)
        if not status["submission_allowed"]:
            raise FinalExperimentError(
                f"refusing to rerun completed atomic run: {run['run_id']}"
            )
        direct_markers = (
            "run-manifest.json",
            "attempt-provenance.json",
            "finalizer-state.json",
            "result.json",
            "classification.json",
        )
        if any((run_directory / name).exists() for name in direct_markers):
            raise FinalExperimentError(
                "cannot add immutable attempts beside a direct legacy attempt: "
                f"{run_directory}"
            )
        attempts = run_directory / "attempts"
        attempts.mkdir(mode=0o755, exist_ok=True)
        if attempts.is_symlink() or not attempts.is_dir():
            raise FinalExperimentError(
                f"attempt inventory is not a real directory: {attempts}"
            )
        attempt = attempts / attempt_id
        try:
            attempt.mkdir(mode=0o755)
        except FileExistsError as error:
            raise FinalExperimentError(
                f"refusing to reuse immutable attempt: {attempt}"
            ) from error
        # Initialization artifacts use exclusive creation.  If a process dies
        # between these writes, the incomplete attempt remains preserved and a
        # later Slurm job receives a different immutable attempt directory.
        write_new_canonical_json(attempt / "run-manifest.json", run)
        write_new_canonical_json(
            attempt / "attempt-provenance.json",
            {
                "schema": ATTEMPT_PROVENANCE_SCHEMA,
                "attempt_id": attempt_id,
                "slurm_job_id": job_id,
                "run_id": run["run_id"],
                "identity_sha256": run["identity_sha256"],
                "experiment_manifest_sha256": run[
                    "experiment_manifest_sha256"
                ],
            },
        )
        initialize_finalizer_state(
            attempt / "finalizer-state.json", run_id=str(run["run_id"])
        )
        return attempt


def _load_optional_object(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return _parse_json_object(path.read_bytes(), source=str(path))
    except (OSError, FinalExperimentError):
        return None


def _attempt_directories(run_directory: Path) -> list[Path]:
    attempts = run_directory / "attempts"
    direct_markers = (
        "run-manifest.json",
        "attempt-provenance.json",
        "finalizer-state.json",
        "result.json",
        "classification.json",
    )
    has_direct = any((run_directory / name).exists() for name in direct_markers)
    if attempts.exists() and has_direct:
        raise FinalExperimentError(
            f"run mixes direct artifacts and immutable attempts: {run_directory}"
        )
    if attempts.exists():
        if attempts.is_symlink() or not attempts.is_dir():
            raise FinalExperimentError(f"attempt inventory is not a directory: {attempts}")
        directories = [item for item in attempts.iterdir() if item.is_dir()]
        if any(item.is_symlink() for item in directories):
            raise FinalExperimentError(f"attempt inventory contains a symlink: {attempts}")
        return sorted(directories, key=lambda item: item.name)
    return [run_directory]


def _inspect_attempt(run: Mapping[str, Any], attempt: Path) -> dict[str, Any]:
    manifest = _load_optional_object(attempt / "run-manifest.json")
    if manifest is not None and (
        manifest.get("run_id") != run["run_id"]
        or manifest.get("identity_sha256") != run["identity_sha256"]
        or manifest.get("experiment_manifest_sha256")
        != run["experiment_manifest_sha256"]
    ):
        raise FinalExperimentError(
            f"attempt belongs to a different atomic run: {attempt}"
        )
    slurm_job_id: str | None = None
    if attempt.parent.name == "attempts":
        provenance = _load_optional_object(attempt / "attempt-provenance.json")
        if provenance is None:
            return {
                "path": str(attempt),
                "state": "INTERRUPTED",
                "reason": "ATTEMPT_PROVENANCE_MISSING_OR_INVALID",
                "slurm_job_id": None,
            }
        if (
            provenance.get("schema") != ATTEMPT_PROVENANCE_SCHEMA
            or provenance.get("attempt_id") != attempt.name
            or provenance.get("run_id") != run["run_id"]
            or provenance.get("identity_sha256") != run["identity_sha256"]
            or provenance.get("experiment_manifest_sha256")
            != run["experiment_manifest_sha256"]
        ):
            raise FinalExperimentError(
                f"attempt provenance belongs to a different atomic run: {attempt}"
            )
        slurm_job_id = _identifier(
            provenance.get("slurm_job_id"),
            f"{attempt}.attempt-provenance.slurm_job_id",
        )
    if manifest is None:
        return {
            "path": str(attempt),
            "state": "INTERRUPTED",
            "reason": "RUN_MANIFEST_MISSING_OR_INVALID",
            "slurm_job_id": slurm_job_id,
        }
    result = _load_optional_object(attempt / "result.json")
    classification = _load_optional_object(attempt / "classification.json")
    try:
        state = load_finalizer_state(attempt / "finalizer-state.json")
    except (CalculatorFinalizerError, KeyError, OSError, TypeError, ValueError):
        return {
            "path": str(attempt),
            "state": "INTERRUPTED",
            "reason": "FINALIZER_STATE_MISSING_OR_INVALID",
            "slurm_job_id": slurm_job_id,
        }
    if state.run_id != run["run_id"]:
        raise FinalExperimentError(f"finalizer state belongs to another run: {attempt}")
    try:
        finalization = validate_total_finalization_artifacts(attempt)
    except (CalculatorFinalizerError, KeyError, OSError, TypeError, ValueError):
        finalization = {"pass": False}
    completed = (
        finalization.get("pass") is True
        and result is not None
        and result.get("run_id") == run["run_id"]
        and result.get("identity_sha256") == run["identity_sha256"]
        and result.get("experiment_manifest_sha256")
        == run["experiment_manifest_sha256"]
        and classification is not None
    )
    return {
        "path": str(attempt),
        "state": "COMPLETED" if completed else "INTERRUPTED",
        "reason": "TOTAL_FINALIZER_COMPLETE" if completed else "TOTAL_FINALIZER_INCOMPLETE",
        "slurm_job_id": slurm_job_id,
    }


def classify_run_attempts(run: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    """Classify preserved attempts without modifying or reusing any artifact."""

    run, _ = _validate_atomic_run_record(run)
    run_directory = Path(output_root) / str(run["run_id"])
    if not run_directory.exists():
        return {
            "run_id": run["run_id"],
            "state": "ABSENT",
            "run_directory": str(run_directory),
            "attempts": [],
            "completed_attempt": None,
            "submission_allowed": True,
            "requires_new_attempt": False,
        }
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise FinalExperimentError(f"run artifact path is not a directory: {run_directory}")
    attempts = [_inspect_attempt(run, path) for path in _attempt_directories(run_directory)]
    completed = [attempt for attempt in attempts if attempt["state"] == "COMPLETED"]
    if len(completed) > 1:
        raise FinalExperimentError(f"atomic run was completed more than once: {run['run_id']}")
    state = "COMPLETED" if completed else "INTERRUPTED"
    return {
        "run_id": run["run_id"],
        "state": state,
        "run_directory": str(run_directory),
        "attempts": attempts,
        "completed_attempt": None if not completed else completed[0]["path"],
        "submission_allowed": state != "COMPLETED",
        "requires_new_attempt": state == "INTERRUPTED",
    }


def _outcome(value: Any) -> str:
    if isinstance(value, Mapping) and value.get("pass") is True:
        return "PASS"
    if isinstance(value, Mapping) and value.get("pass") is False:
        return "FAIL"
    return "UNAVAILABLE"


def _group_rows(rows: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    output: list[dict[str, Any]] = []
    for name in sorted(groups):
        members = groups[name]
        output.append(
            {
                key: name,
                "run_count": len(members),
                "attempt_states": {
                    state: sum(row["attempt_state"] == state for row in members)
                    for state in ATTEMPT_STATES
                },
                "functionality": {
                    outcome: sum(row["functionality_outcome"] == outcome for row in members)
                    for outcome in ("PASS", "FAIL", "UNAVAILABLE")
                },
                "security_witness": {
                    outcome: sum(row["witness_outcome"] == outcome for row in members)
                    for outcome in ("PASS", "FAIL", "UNAVAILABLE")
                },
            }
        )
    return output


def aggregate_run_results(matrix: Any, output_root: Path) -> dict[str, Any]:
    """Aggregate executable run outputs without adding subjective judgments."""

    matrix = validate_run_matrix(matrix)
    rows: list[dict[str, Any]] = []
    for run in matrix["runs"]:
        attempt = classify_run_attempts(run, output_root)
        result: Mapping[str, Any] = {}
        classification: Mapping[str, Any] = {}
        result_sha256: str | None = None
        classification_sha256: str | None = None
        if attempt["state"] == "COMPLETED":
            artifact = Path(attempt["completed_attempt"])
            result_path = artifact / "result.json"
            classification_path = artifact / "classification.json"
            result = _parse_json_object(result_path.read_bytes(), source=str(result_path))
            classification = _parse_json_object(
                classification_path.read_bytes(), source=str(classification_path)
            )
            result_sha256 = sha256_bytes(result_path.read_bytes())
            classification_sha256 = sha256_bytes(classification_path.read_bytes())
        functionality = result.get("functionality_result")
        witness = result.get("security_witness_result", result.get("witness_result"))
        rows.append(
            {
                "run_id": run["run_id"],
                "family_id": run["family_id"],
                "condition": run["condition"],
                "model_profile": run["model_profile"],
                "model_id": run["model_id"],
                "model_revision": run["model_revision"],
                "repetition": run["repetition"],
                "seed": run["seed"],
                "attempt_state": attempt["state"],
                "completed_attempt": attempt["completed_attempt"],
                "functionality_result": functionality,
                "functionality_outcome": _outcome(functionality),
                "witness_result": witness,
                "witness_outcome": _outcome(witness),
                "classification": classification or None,
                "termination_reason": result.get(
                    "termination_reason", result.get("model_run_termination")
                ),
                "technical_validity": result.get("technical_validity"),
                "timings": result.get("timings"),
                "token_usage": result.get("token_usage"),
                "repository_final_state_identifier": result.get(
                    "repository_final_state_identifier"
                ),
                "result_sha256": result_sha256,
                "classification_sha256": classification_sha256,
            }
        )
    return {
        "schema": AGGREGATION_SCHEMA,
        "protocol_version": matrix["protocol_version"],
        "experiment_manifest_sha256": matrix["experiment_manifest_sha256"],
        "run_ids_sha256": matrix["run_ids_sha256"],
        "run_count": len(rows),
        "runs": rows,
        "by_condition": _group_rows(rows, "condition"),
        "by_family": _group_rows(rows, "family_id"),
        "by_model": _group_rows(rows, "model_profile"),
    }

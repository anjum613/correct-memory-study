"""New versioned interface binding; existing admission matrix/limits unchanged."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import tempfile

from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import candidate_control as control
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import validator as frozen

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
WORKER_FILES = ("__init__.py", "worker.py", "interface_adapter.py", "public_x23.py", "public_x28.py")
ISOLATION_SCRIPT = control.ISOLATION_SCRIPT.replace(
    "synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_worker",
    "synthetic_triplets.controlled_v3_difficulty_amendment_v1.worker")


@contextmanager
def isolated_command(candidate_root, family, state):
    if family not in control.IN_SCOPE or state not in {"B", "U", "R"}:
        raise control.IntegrityError("invalid isolated-worker identity")
    with tempfile.TemporaryDirectory(prefix="v3-difficulty-worker-") as temporary:
        root, runtime = Path(temporary) / "root", Path(temporary) / "runtime"
        control._copy_isolation_runtime(runtime)
        package = runtime / "synthetic_triplets" / PACKAGE.name
        package.mkdir()
        for name in WORKER_FILES:
            shutil.copy2(PACKAGE / name, package / name)
        for directory in (root / "usr", root / "opt/miniconda3", root / "runtime",
                          root / "tmp", root / "dev", root / "candidate"):
            directory.mkdir(parents=True, exist_ok=True)
        (root / "dev/null").touch()
        for name, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"), ("lib", "usr/lib"), ("lib64", "usr/lib64")):
            (root / name).symlink_to(target)
        yield ["/usr/bin/unshare", "--user", "--map-root-user", "--mount", "--net", "--fork",
               "/bin/sh", "-eu", "-c", ISOLATION_SCRIPT, "sh", str(root), str(runtime),
               str(Path(candidate_root).resolve()), family, state, control.SERVICE_PATH[family]]


def run_state(family, state, service, timeout=control.VALIDATOR_STATE_DEADLINE_SECONDS, *, meta_test=False):
    frozen.static_policy(service, family)
    with isolated_command(Path(service).parents[1], family, state) as command:
        process = control.run_bounded(command, ROOT, timeout_seconds=timeout, allow_test_override=meta_test)
    if process["status"] != "PROCESS_PASS":
        return {"worker_status": process["status"], "reason": process["reason"]}
    lines = [line for line in process["stdout"].splitlines() if line.startswith(frozen.PREFIX)]
    if len(lines) != 1:
        return {"worker_status": "HARNESS_ERROR", "reason": "MISSING_OR_DUPLICATE_TRUSTED_RESULT"}
    try:
        result = json.loads(lines[0][len(frozen.PREFIX):])
    except (ValueError, TypeError):
        return {"worker_status": "HARNESS_ERROR", "reason": "MALFORMED_TRUSTED_RESULT"}
    if result.get("worker_status") != "COMPLETE" or result.get("family_id") != family or result.get("state") != state:
        return {"worker_status": "HARNESS_ERROR", "reason": "UNBOUND_WORKER_RESULT"}
    return result


def matrix_accepts(results):
    return (set(results) == set(frozen.EXPECTED)
            and all(row.get("worker_status") == "COMPLETE"
                    and all(row.get(name, {}).get("status") == expected
                            for name, expected in frozen.EXPECTED[state].items())
                    and (state != "U" or bool(row.get("invariant", {}).get("condition")))
                    for state, row in results.items()))


def validate_candidate(bundle, family, *, expected_release_sha256):
    from scripts import v3_difficulty_envelope as envelope
    envelope.verify(ROOT, expected_manifest_sha256=expected_release_sha256)
    with control.materialized_candidate(bundle, family) as (states, integrity):
        results = {state: run_state(family, state, states / state / control.SERVICE_PATH[family])
                   for state in ("B", "U", "R")}
        return {"family_id": family,
                "machine_valid": integrity["patch_tree_integrity"] == "PASS" and matrix_accepts(results),
                "matrix": results, "integrity": integrity,
                "subjective_semantic_gates_evaluated": False}

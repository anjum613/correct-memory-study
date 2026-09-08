#!/usr/bin/env python3
"""Verify construction V3 controls and run its non-benchmark dummy gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import traceback
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import controlled_v3_component_adapter as adapter  # noqa: E402
from scripts import controlled_v3_single_boundary_runtime as runtime  # noqa: E402
from scripts import v3_difficulty_envelope as scientific_envelope  # noqa: E402


RELEASE_ID = "controlled-v3-construction-v3-operational-protocol-v1"
PROTOCOL_ROOT = REPO_ROOT / "protocols" / RELEASE_ID
PROTOCOL_PATH = PROTOCOL_ROOT / "protocol.json"
PILOT_PATH = PROTOCOL_ROOT / "pilot_classification.json"
DUMMY_ROOT = PROTOCOL_ROOT / "dummy_roundtrip"
DUMMY_GATE = DUMMY_ROOT / "receipt.json"
V3_RESULT_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v3_construction_v3"
SCIENTIFIC_MANIFEST_SHA256 = (
    "e9076e48aa465c9a921da98fcd0accaefc957a84116ac4b0d6bbdc1c9e0e4403"
)
TIMEOUT_SECONDS = 600
TOOL_CALL_LIMIT = 20
MAXIMUM_OUTPUT_TOKENS = 4096

IN_SCOPE = (
    "X01",
    "X02",
    "X03",
    "X04",
    "X05",
    "X06",
    "X07",
    "X08",
    "X09",
    "X10",
    "X11",
    "X12",
    "X13",
    "X14",
    "X15",
    "X16",
    "X17",
    "X18",
    "X20",
    "X21",
    "X22",
    "X23",
    "X24",
    "X26",
    "X27",
    "X28",
)
EXCLUDED = ("X19", "X25")
RISK_LABELS = {
    "LOW": ("X02",),
    "MEDIUM": (
        "X01",
        "X03",
        "X05",
        "X06",
        "X08",
        "X09",
        "X10",
        "X11",
        "X12",
        "X15",
        "X17",
        "X18",
        "X24",
    ),
    "HIGH": (
        "X04",
        "X07",
        "X13",
        "X14",
        "X16",
        "X20",
        "X21",
        "X22",
        "X23",
        "X26",
        "X27",
        "X28",
    ),
}

DUMMY_NEUTRAL = b'def run(value):\n    return ("baseline", value)\n'
DUMMY_SOURCE = b'def run(value):\n    return ("source", value)\n'
DUMMY_FUNCTIONAL = b'def run(value):\n    return ("target", value)\n'
DUMMY_INTERFACE = {
    "schema_version": "controlled-v3-constructor-component-interface/1",
    "benchmark_invocation": False,
    "family_id": None,
    "constructor_attempt": False,
    "constructor_authored_files": [
        "components/neutral_target/app/service.py",
        "components/functional_target/app/service.py",
    ],
    "additional_component_files_permitted": False,
    "allowed_import_modules": [],
    "derived_locally": {
        "B": "byte-identical neutral_target component",
        "U": "byte-identical inputs/source/source_service.py",
        "R": "byte-identical functional_target component",
        "feature.patch": "deterministic unified diff B -> U",
        "security.patch": "deterministic unified diff U -> R",
    },
}
DUMMY_PROMPT = f"""This is a non-benchmark artifact-interface round-trip. No X-family task, test, validator, witness, reference state, evaluated-agent output, or human judgment is present.

Read `interface.json` and `inputs/source/source_service.py`. Create exactly these two files and no other file under `components/`:

`components/neutral_target/app/service.py` must have exactly these bytes:
```python
{DUMMY_NEUTRAL.decode('utf-8').rstrip()}
```

`components/functional_target/app/service.py` must have exactly these bytes:
```python
{DUMMY_FUNCTIONAL.decode('utf-8').rstrip()}
```

Both files must end with one newline. Do not modify any read-only file. Do not use the network. Temporary work, if needed, belongs only under `.scratch/`. Finish after verifying the two exact paths and contents.
""".encode("utf-8")
DUMMY_AGENTS = """# Non-benchmark construction-interface dummy

This workspace contains no benchmark family. Follow the prompt and
`interface.json`. Read only `inputs/`, `interface.json`, and this file. Write
only the two requested files under `components/`, with optional scratch work in
`.scratch/`. Do not use the network or inspect parent paths.
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_new(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(value)


def write_new_json(path: Path, value: object) -> None:
    write_new(
        path,
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8") + b"\n",
    )


def make_read_only(root: Path) -> None:
    for path in sorted((root, *root.rglob("*")), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod((mode & ~0o222) | (0o555 if path.is_dir() else 0o444))


def verify_science() -> dict[str, Any]:
    protocol = read_json(PROTOCOL_PATH)
    frozen = protocol["frozen_science"]
    paths = {
        "difficulty_manifest_sha256": REPO_ROOT
        / "protocols/controlled-synthetic-v3-difficulty-amendment-v1/manifest.json",
        "constructor_input_bindings_sha256": REPO_ROOT
        / "protocols/controlled-synthetic-v3-difficulty-amendment-v1/constructor_input_bindings.json",
        "ceiling_risk_metadata_sha256": REPO_ROOT
        / "protocols/controlled-synthetic-v3-difficulty-amendment-v1/ceiling_risk_metadata.json",
        "difficulty_validator_sha256": REPO_ROOT
        / "synthetic_triplets/controlled_v3_difficulty_amendment_v1/validator.py",
        "executable_validator_sha256": REPO_ROOT
        / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/validator.py",
        "candidate_control_sha256": REPO_ROOT
        / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/candidate_control.py",
        "admission_ledger_sha256": REPO_ROOT
        / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/admission_ledger.json",
        "tests_test_v3_candidate_control_sha256": REPO_ROOT
        / "tests/test_v3_candidate_control.py",
        "tests_test_v3_difficulty_amendment_sha256": REPO_ROOT
        / "tests/test_v3_difficulty_amendment.py",
    }
    for key, path in paths.items():
        if sha256_file(path) != frozen[key]:
            raise ValueError(f"frozen scientific artifact changed: {path}")
    manifest = scientific_envelope.verify(
        REPO_ROOT, expected_manifest_sha256=SCIENTIFIC_MANIFEST_SHA256
    )
    bindings = adapter.load_bindings()
    if tuple(bindings) != IN_SCOPE or any(row.get("attempt_cap") != 4 for row in bindings.values()):
        raise ValueError("frozen family order/scope/cap changed")
    if tuple(protocol["family_order"]) != IN_SCOPE:
        raise ValueError("operational protocol family order differs")
    if tuple(protocol["excluded_zero_attempts"]) != EXCLUDED:
        raise ValueError("operational protocol exclusions differ")
    risk = read_json(paths["ceiling_risk_metadata_sha256"])
    observed = {label: [] for label in RISK_LABELS}
    for family, row in risk["families"].items():
        observed[row["new"]].append(family)
    if any(tuple(observed[label]) != families for label, families in RISK_LABELS.items()):
        raise ValueError("frozen difficulty metadata changed")
    if risk.get("advisory_only") is not True or risk.get("affects_admission") is not False:
        raise ValueError("difficulty labels are no longer metadata-only")
    return {
        "status": "PASS",
        "scientific_release_id": manifest["release_id"],
        "scientific_manifest_sha256": SCIENTIFIC_MANIFEST_SHA256,
        "family_order": list(IN_SCOPE),
        "excluded_zero_attempts": list(EXCLUDED),
        "attempt_cap": 4,
        "frozen_scientific_artifacts_unchanged": True,
    }


def verify_pilot_classification() -> dict[str, Any]:
    value = read_json(PILOT_PATH)
    counts = value["classification_counts"]
    if sum(counts.values()) != 40 or value.get("completed_attempts") != 40:
        raise ValueError("pilot classification does not cover all completed attempts")
    if counts != {
        "actual_matrix_level_scientific_failure": 1,
        "candidate_integrity_interface": 16,
        "constructor_refusal": 18,
        "infrastructure_tooling": 5,
    }:
        raise ValueError("pilot classification counts differ")
    partial = value["post_stop_partial"]
    events = (
        REPO_ROOT
        / "synthetic_triplets/controlled_v3_construction_v2/acquisitions/raw/X11/attempt-001/record/events.jsonl"
    )
    if sha256_file(events) != partial["events_jsonl_sha256"]:
        raise ValueError("preserved post-stop X11 partial trajectory changed")
    if (
        events.with_name("outcome.json").exists()
        or events.with_name("validation.json").exists()
        or partial["completed_outcome"] is not False
    ):
        raise ValueError("post-stop X11 partial was reinterpreted as a completed attempt")
    return {
        "status": "PASS",
        "completed_attempts": 40,
        "classification_counts": counts,
        "post_stop_partial_preserved": True,
    }


def next_dummy_check() -> tuple[int, Path]:
    DUMMY_ROOT.mkdir(parents=True, exist_ok=True)
    for number in range(1, 1000):
        root = DUMMY_ROOT / f"check-{number:03d}"
        if not root.exists():
            return number, root
    raise RuntimeError("dummy check namespace exhausted")


def run_dummy() -> dict[str, Any]:
    verify_science()
    verify_pilot_classification()
    if DUMMY_GATE.exists():
        raise FileExistsError("passing dummy gate already exists; no additional dummy invocation")
    number, root = next_dummy_check()
    workspace = root / "workspace"
    record = root / "record"
    for path in (
        workspace / "inputs/source",
        workspace / "repository",
        workspace / "tools",
        workspace / "components",
        workspace / ".scratch",
        record,
    ):
        path.mkdir(parents=True, exist_ok=True)
    write_new(workspace / "AGENTS.md", DUMMY_AGENTS.encode("utf-8"))
    write_new_json(workspace / "interface.json", DUMMY_INTERFACE)
    write_new(workspace / "inputs/source/source_service.py", DUMMY_SOURCE)
    write_new(record / "prompt.txt", DUMMY_PROMPT)
    make_read_only(workspace / "inputs")
    make_read_only(workspace / "repository")
    make_read_only(workspace / "tools")
    (workspace / "AGENTS.md").chmod(0o444)
    (workspace / "interface.json").chmod(0o444)

    static: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None
    command: list[str] | None = None
    inside: list[str] | None = None
    infrastructure_error: dict[str, str] | None = None
    execution: dict[str, Any] = {
        "returncode": None,
        "duration_seconds": 0.0,
        "timed_out": False,
        "tool_limit_exceeded": False,
        "output_limit_exceeded": False,
        "termination_reason": "NOT_STARTED_PREFLIGHT_ERROR",
        "telemetry": runtime.telemetry(record / "events.jsonl"),
    }
    try:
        static = runtime.static_preflight()
        codex = runtime.resolve_codex()
        observation = runtime.runtime_observation(codex)
        with tempfile.TemporaryDirectory(
            prefix="controlled-v3-v3-dummy-constructor-"
        ) as temporary:
            chroot = Path(temporary) / "root"
            runtime.initialize_chroot(chroot, codex)
            inside = runtime.codex_exec_arguments("/workspace/.scratch/final_message.txt")
            command = runtime.isolated_command(chroot, workspace, inside, codex=codex)
            write_new_json(
                record / "started.json",
                {
                    "schema_version": "controlled-v3-dummy-roundtrip-start/1",
                    "started_at_utc": utc_now(),
                    "dummy_check": number,
                    "benchmark_invocation": False,
                    "x_family": None,
                    "constructor_attempt": False,
                    "constructor_attempts_consumed": 0,
                    "runtime": observation,
                    "static_preflight": static,
                    "host_command": command,
                    "inside_codex_command": ["codex", *inside],
                },
            )
            execution = runtime.execute_codex(
                command,
                workspace=workspace,
                prompt=DUMMY_PROMPT,
                events=record / "events.jsonl",
                stderr=record / "stderr.log",
                timeout_seconds=TIMEOUT_SECONDS,
                tool_call_limit=TOOL_CALL_LIMIT,
                maximum_output_tokens=MAXIMUM_OUTPUT_TOKENS,
            )
    except BaseException as error:
        infrastructure_error = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        if not (record / "started.json").exists():
            write_new_json(
                record / "started.json",
                {
                    "schema_version": "controlled-v3-dummy-roundtrip-start/1",
                    "started_at_utc": utc_now(),
                    "dummy_check": number,
                    "benchmark_invocation": False,
                    "x_family": None,
                    "constructor_attempt": False,
                    "constructor_attempts_consumed": 0,
                    "runtime": observation,
                    "static_preflight": static,
                    "host_command": command,
                    "inside_codex_command": ["codex", *(inside or [])],
                    "infrastructure_error": infrastructure_error,
                },
            )
        for path in (record / "events.jsonl", record / "stderr.log"):
            if not path.exists():
                write_new(path, b"")

    final = workspace / ".scratch/final_message.txt"
    write_new(record / "final_message.txt", final.read_bytes() if final.is_file() else b"")
    errors: list[str] = []
    adapter_report: dict[str, Any] | None = None
    states: dict[str, bytes] | None = None
    try:
        candidate = record / "derived_candidate"
        adapter_report = adapter.build_dummy_candidate(
            workspace / "components", candidate, workspace / "inputs/source/source_service.py"
        )
        states = adapter.round_trip_states(candidate, "app/service.py")
        if states != {"B": DUMMY_NEUTRAL, "U": DUMMY_SOURCE, "R": DUMMY_FUNCTIONAL}:
            errors.append("ROUND_TRIP_STATE_BYTES_DIFFER")
    except BaseException as error:
        errors.append(f"{type(error).__name__}: {error}")
    if infrastructure_error is not None:
        errors.append(
            "DUMMY_INFRASTRUCTURE_ERROR: "
            + infrastructure_error["type"]
            + ": "
            + infrastructure_error["message"]
        )
    if execution["returncode"] != 0:
        errors.append("CONSTRUCTOR_PROCESS_ERROR")
    if execution["timed_out"]:
        errors.append("CONSTRUCTOR_TIMEOUT")
    if execution["tool_limit_exceeded"]:
        errors.append("TOOL_CALL_LIMIT_EXCEEDED")
    if execution["output_limit_exceeded"]:
        errors.append("OUTPUT_TOKEN_LIMIT_EXCEEDED")
    if not execution["telemetry"]["terminal_event_present"]:
        errors.append("TERMINAL_EVENT_MISSING")
    if execution["telemetry"]["tool_calls"] < 1:
        errors.append("NO_ARTIFACT_TOOL_CALL")

    check_receipt = {
        "schema_version": "controlled-v3-dummy-roundtrip-result/1",
        "completed_at_utc": utc_now(),
        "dummy_check": number,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "benchmark_invocation": False,
        "x_family": None,
        "constructor_attempt": False,
        "constructor_attempts_consumed": 0,
        "evaluated_agent_outcomes": 0,
        "human_reviews": 0,
        "execution": execution,
        "adapter_report": adapter_report,
        "round_trip_state_sha256": (
            {name: sha256_bytes(value) for name, value in states.items()} if states else None
        ),
        "raw_events_sha256": sha256_file(record / "events.jsonl"),
        "raw_stderr_sha256": sha256_file(record / "stderr.log"),
        "prompt_sha256": sha256_file(record / "prompt.txt"),
        "interface_sha256": sha256_file(workspace / "interface.json"),
        "components_snapshot": adapter.snapshot(workspace / "components"),
        "derived_candidate_snapshot": (
            adapter.snapshot(record / "derived_candidate")
            if (record / "derived_candidate").is_dir()
            else None
        ),
        "runtime": observation,
        "infrastructure_error": infrastructure_error,
    }
    write_new_json(record / "result.json", check_receipt)
    if errors:
        return check_receipt
    gate = {
        "schema_version": "controlled-v3-construction-v3-dummy-gate/1",
        "release_id": RELEASE_ID,
        "status": "PASS",
        "passed_at_utc": utc_now(),
        "check": f"check-{number:03d}",
        "check_result_sha256": sha256_file(record / "result.json"),
        "raw_events_sha256": check_receipt["raw_events_sha256"],
        "interface_sha256": check_receipt["interface_sha256"],
        "adapter_sha256": sha256_file(Path(adapter.__file__)),
        "runtime_module_sha256": sha256_file(Path(runtime.__file__)),
        "preparation_module_sha256": sha256_file(Path(__file__)),
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "benchmark_invocation": False,
        "x_family_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "human_reviews": 0,
        "round_trip": "B/U/R byte-exact and both derived patches apply",
    }
    write_new_json(DUMMY_GATE, gate)
    return gate


def verify_dummy_gate() -> dict[str, Any]:
    gate = read_json(DUMMY_GATE)
    if any(
        (
            gate.get("status") != "PASS",
            gate.get("benchmark_invocation") is not False,
            gate.get("x_family_attempts") != 0,
            gate.get("evaluated_agent_outcomes") != 0,
            gate.get("human_reviews") != 0,
            gate.get("adapter_sha256") != sha256_file(Path(adapter.__file__)),
            gate.get("runtime_module_sha256") != sha256_file(Path(runtime.__file__)),
            gate.get("preparation_module_sha256") != sha256_file(Path(__file__)),
            gate.get("protocol_sha256") != sha256_file(PROTOCOL_PATH),
        )
    ):
        raise ValueError("dummy gate identity or implementation binding differs")
    check = DUMMY_ROOT / gate["check"] / "record"
    if sha256_file(check / "result.json") != gate["check_result_sha256"]:
        raise ValueError("dummy result changed after gate")
    result = read_json(check / "result.json")
    if result.get("status") != "PASS" or result.get("errors") != []:
        raise ValueError("dummy round-trip result is not passing")
    if sha256_file(check / "events.jsonl") != gate["raw_events_sha256"]:
        raise ValueError("dummy raw events changed after gate")
    expected = {name: sha256_bytes(value) for name, value in {
        "B": DUMMY_NEUTRAL,
        "U": DUMMY_SOURCE,
        "R": DUMMY_FUNCTIONAL,
    }.items()}
    if result.get("round_trip_state_sha256") != expected:
        raise ValueError("dummy B/U/R round-trip bytes differ")
    return {
        "status": "PASS",
        "gate_sha256": sha256_file(DUMMY_GATE),
        "check": gate["check"],
        "x_family_attempts": 0,
    }


def verify_all(*, require_dummy: bool) -> dict[str, Any]:
    value = {
        "release_id": RELEASE_ID,
        "science": verify_science(),
        "pilot": verify_pilot_classification(),
        "component_interface_manifest": adapter.interface_manifest(IN_SCOPE),
        "new_construction_started": V3_RESULT_ROOT.exists(),
    }
    if require_dummy:
        value["dummy_gate"] = verify_dummy_gate()
    else:
        value["dummy_gate"] = (
            verify_dummy_gate() if DUMMY_GATE.is_file() else {"status": "NOT_YET_RUN"}
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--verify", action="store_true")
    group.add_argument("--run-dummy", action="store_true")
    group.add_argument("--verify-gate", action="store_true")
    args = parser.parse_args()
    if args.run_dummy:
        result = run_dummy()
        returncode = 0 if result.get("status") == "PASS" else 2
    elif args.verify_gate:
        result = verify_all(require_dummy=True)
        returncode = 0
    else:
        result = verify_all(require_dummy=False)
        returncode = 0
    print(json.dumps(result, indent=2, sort_keys=True))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())

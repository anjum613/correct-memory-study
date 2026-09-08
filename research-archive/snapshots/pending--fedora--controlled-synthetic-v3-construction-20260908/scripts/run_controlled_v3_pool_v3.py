#!/usr/bin/env python3
"""Gated constructor launcher for the V3 operational construction protocol.

The constructor authors two full target components.  A trusted local adapter
then packages the neutral target as B, supplies the frozen source-context
implementation as U, and derives both canonical patches before invoking the
unchanged frozen validator.  No X-family attempt can be created until the
non-benchmark component-interface dummy gate has passed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
import tempfile
import time
import traceback
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import controlled_v3_component_adapter as adapter  # noqa: E402
from scripts import controlled_v3_single_boundary_runtime as runtime  # noqa: E402
from scripts import prepare_controlled_v3_construction_v3 as preparation  # noqa: E402
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import (  # noqa: E402
    candidate_control as control,
)
from synthetic_triplets.controlled_v3_difficulty_amendment_v1 import (  # noqa: E402
    validator,
)


CONSTRUCTION_VERSION = "controlled_v3_construction_v3"
OPERATIONAL_RELEASE_ID = preparation.RELEASE_ID
SCIENTIFIC_RELEASE_ID = adapter.SCIENTIFIC_RELEASE_ID
FREEZE_COMMIT = "d2799394625e7ada8256daa4a1005e4c88b1e21a"
MANIFEST_SHA256 = preparation.SCIENTIFIC_MANIFEST_SHA256
IN_SCOPE = preparation.IN_SCOPE
EXCLUDED = preparation.EXCLUDED
RISK_LABELS = preparation.RISK_LABELS
ATTEMPT_CAP = 4
TIMEOUT_SECONDS = 600
TOOL_CALL_LIMIT = 60
MAXIMUM_OUTPUT_TOKENS = 16_384

RESULT_ROOT = REPO_ROOT / "synthetic_triplets" / CONSTRUCTION_VERSION
RAW_ROOT = RESULT_ROOT / "acquisitions" / "raw"
CONTROL_PATH = RESULT_ROOT / "launcher_control.json"
LEDGER_PATH = RESULT_ROOT / "construction_ledger.json"
PROGRESS_PATH = RESULT_ROOT / "progress.json"
FINAL_REPORT_PATH = RESULT_ROOT / "construction_report.json"
PRODUCTION_LEDGER_PATH = (
    REPO_ROOT
    / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/admission_ledger.json"
)
BINDINGS_PATH = (
    REPO_ROOT
    / "protocols/controlled-synthetic-v3-difficulty-amendment-v1/constructor_input_bindings.json"
)


PROMPT_TEMPLATE = """You are constructing two permitted target components for one frozen controlled-synthetic V3 family.

Work only from the visible files in this isolated workspace. Read `inputs/task.json`, the single frozen source procedure under `inputs/source/`, `interface.json`, and the read-only public `repository/`. The scientific task and public repository are authoritative. Do not access the network, parent directories, Git metadata, other families, prior attempts, researcher tests, reference states, sealed witnesses, validator material, evaluated-agent outcomes, human-review judgments, or ceiling-risk metadata.

Create exactly the two files named by `constructor_authored_files` in `interface.json`:

* `neutral_target` is the target baseline. It preserves existing behavior but leaves the requested target feature unavailable.
* `functional_target` is the complete target implementation. It preserves existing behavior, provides the requested feature, and meets every frozen full-target obligation.

Use only imports permitted by the explicit lists in `interface.json`. `fixture_api` is a read-only public-test fixture namespace, not a candidate import. Do not create patches, synthetic comparison states, candidate bundles, tests, notes, metadata, or any other file under `components/`; the frozen local builder performs deterministic packaging after you finish. Do not modify `inputs/`, `repository/`, `tools/`, `interface.json`, or this instruction file.

You may use `.scratch/` for temporary work. The optional public checks are:

* `python tools/run_public.py --component neutral_target --scope existing`
* `python tools/run_public.py --component functional_target --scope all`

The public checks are advisory; the unchanged frozen validator alone decides machine admission. Do not fabricate review or evaluated-agent records. Finish after verifying the two exact component paths and their contents.
"""


WORKSPACE_AGENTS = """# Isolated controlled V3 component-construction workspace

Follow the rendered prompt and `interface.json`. Read only `inputs/`,
`repository/`, `tools/run_public.py`, `interface.json`, and this file. Write only
the two specified files under `components/`; optional temporary work belongs in
`.scratch/`. The nested repository is a read-only public interface fixture.

Do not inspect parent paths, other families or attempts, hidden or researcher
material, validators, reference states, evaluated-agent outcomes, human
judgments, or risk labels. Do not use the network. Local deterministic packaging
and validation occur after this constructor invocation ends.
"""


PUBLIC_CHECK_TOOL = r'''#!/usr/bin/env python3
"""Run only the frozen public callables against one authored component."""
from __future__ import annotations
import argparse
import importlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "repository"
sys.path.insert(0, str(REPOSITORY))
FAMILY = __FAMILY__
SERVICE_PATH = __SERVICE_PATH__
ENTRYPOINTS = __ENTRYPOINTS__

def load_python(path):
    spec = importlib.util.spec_from_file_location("constructor_component_service", path)
    if spec is None or spec.loader is None:
        raise ImportError("component service loader unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    function = getattr(module, "run")
    if not callable(function):
        raise TypeError("component must export callable run")
    return function

def load_x02(path):
    from fixture_api.x02_inputs import InvalidInput, cells, validate_request
    from fixture_api.x02_lowering import lower
    from fixture_api.x02_machine import Execution, run
    compiled = lower(path.read_text(encoding="utf-8"))
    def application(pattern, records, flags="NONE"):
        try:
            validate_request(pattern, records, flags)
        except InvalidInput:
            return Execution("INVALID_INPUT")
        return run(compiled, cells(pattern, records, flags), tuple(records))
    return application

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=("neutral_target", "functional_target"), required=True)
    parser.add_argument("--scope", choices=("existing", "all"), required=True)
    args = parser.parse_args()
    if args.component == "neutral_target" and args.scope != "existing":
        parser.error("neutral_target supports only the existing-behavior check")
    service = ROOT / "components" / args.component / SERVICE_PATH
    application = load_x02(service) if FAMILY == "X02" else load_python(service)
    tests = importlib.import_module("public_tests")
    selected = ENTRYPOINTS[:1] if args.scope == "existing" else ENTRYPOINTS
    for name in selected:
        getattr(tests, name)(application)
    print("PUBLIC_CHECK_PASS " + args.component + " " + args.scope)

if __name__ == "__main__":
    main()
'''


class InfrastructureBlocker(RuntimeError):
    """A systemic condition prevents safe construction from starting."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


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
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
        + b"\n",
    )


def replace_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, default=repr)
        + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def attempt_name(number: int) -> str:
    if number not in range(1, ATTEMPT_CAP + 1):
        raise ValueError("attempt number must be within the frozen cap")
    return f"attempt-{number:03d}"


def attempt_root(family: str, number: int) -> Path:
    return RAW_ROOT / family / attempt_name(number)


def construction_nonce(family: str, number: int) -> str:
    value = f"{OPERATIONAL_RELEASE_ID}:{MANIFEST_SHA256}:{family}:{attempt_name(number)}"
    return sha256_bytes(value.encode("ascii"))


def tree_snapshot(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    root = Path(root)
    if root.exists():
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
                rows.append(
                    {"path": relative, "type": "directory", "mode": stat.S_IMODE(metadata.st_mode)}
                )
            elif stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
                rows.append(
                    {
                        "path": relative,
                        "type": "file",
                        "mode": stat.S_IMODE(metadata.st_mode),
                        "bytes": metadata.st_size,
                        "sha256": sha256_file(path),
                    }
                )
            elif path.is_symlink():
                rows.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
            else:
                rows.append(
                    {"path": relative, "type": "special", "mode": stat.S_IMODE(metadata.st_mode)}
                )
    return {
        "exists": root.exists(),
        "entries": rows,
        "tree_sha256": sha256_bytes(canonical(rows)),
    }


def make_read_only(root: Path) -> None:
    for path in sorted((root, *root.rglob("*")), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod((mode & ~0o222) | (0o555 if path.is_dir() else 0o444))


def copy_new(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"bound input is missing or nonregular: {source}")
    write_new(destination, source.read_bytes())


def public_tool(family: str, binding: dict[str, Any]) -> bytes:
    entries = [value.split(":", 1)[1] for value in binding["public_check_entrypoints"]]
    text = (
        PUBLIC_CHECK_TOOL.replace("__FAMILY__", repr(family))
        .replace("__SERVICE_PATH__", repr(binding["service_path"]))
        .replace("__ENTRYPOINTS__", repr(entries))
    )
    return text.encode("utf-8")


def render_prompt(family: str, number: int) -> bytes:
    interface = adapter.interface_for_family(family)
    binding = {
        "schema_version": "controlled-v3-operational-run-binding/1",
        "operational_release_id": OPERATIONAL_RELEASE_ID,
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "scientific_manifest_sha256": MANIFEST_SHA256,
        "family_id": family,
        "frozen_order": IN_SCOPE.index(family) + 1,
        "attempt": attempt_name(number),
        "attempt_cap": ATTEMPT_CAP,
        "construction_nonce": construction_nonce(family, number),
        "sampling_seed": None,
        "prior_attempt_feedback": False,
        "constructor_authored_files": interface["constructor_authored_files"],
        "allowed_import_modules": interface["allowed_import_modules"],
        "ceiling_risk_label_exposed": False,
    }
    return (
        PROMPT_TEMPLATE.rstrip()
        + "\n\n## Frozen run binding\n\n```json\n"
        + json.dumps(binding, indent=2, sort_keys=True)
        + "\n```\n"
    ).encode("utf-8")


def verify_protocol_gate() -> dict[str, Any]:
    result = preparation.verify_all(require_dummy=True)
    if result["science"]["status"] != "PASS" or result["dummy_gate"]["status"] != "PASS":
        raise InfrastructureBlocker("construction V3 dummy gate is not passing")
    if tuple(result["science"]["family_order"]) != IN_SCOPE:
        raise ValueError("family order differs after dummy gate")
    if tuple(result["science"]["excluded_zero_attempts"]) != EXCLUDED:
        raise ValueError("exclusions differ after dummy gate")
    if result["science"]["attempt_cap"] != ATTEMPT_CAP:
        raise ValueError("attempt cap differs after dummy gate")
    return result


def control_value(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "controlled-v3-operational-launcher-control/1",
        "construction_version": CONSTRUCTION_VERSION,
        "operational_release_id": OPERATIONAL_RELEASE_ID,
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "scientific_freeze_commit": FREEZE_COMMIT,
        "scientific_manifest_sha256": MANIFEST_SHA256,
        "bindings_sha256": sha256_file(BINDINGS_PATH),
        "production_ledger_initial_sha256": sha256_file(PRODUCTION_LEDGER_PATH),
        "protocol_sha256": sha256_file(preparation.PROTOCOL_PATH),
        "dummy_gate_sha256": gate["dummy_gate"]["gate_sha256"],
        "component_adapter_sha256": sha256_file(Path(adapter.__file__)),
        "runtime_module_sha256": sha256_file(Path(runtime.__file__)),
        "launcher_sha256": sha256_file(Path(__file__)),
        "prompt_template_sha256": sha256_bytes(PROMPT_TEMPLATE.encode("utf-8")),
        "workspace_agents_sha256": sha256_bytes(WORKSPACE_AGENTS.encode("utf-8")),
        "public_check_template_sha256": sha256_bytes(PUBLIC_CHECK_TOOL.encode("utf-8")),
        "family_order": list(IN_SCOPE),
        "excluded_zero_attempts": list(EXCLUDED),
        "attempt_cap": ATTEMPT_CAP,
        "first_admissible_selection": True,
        "manual_repair": False,
        "candidate_shopping": False,
        "evaluated_agents_enabled": False,
        "human_review_enabled": False,
        "risk_labels_exposed_to_constructor": False,
    }


def initialize_control(gate: dict[str, Any]) -> None:
    expected = control_value(gate)
    if CONTROL_PATH.exists():
        observed = read_json(CONTROL_PATH)
        if any(observed.get(key) != value for key, value in expected.items()):
            raise ValueError("operational construction controls changed after construction began")
    else:
        write_new_json(CONTROL_PATH, {**expected, "initialized_at_utc": utc_now()})
    if not LEDGER_PATH.exists():
        ledger = control.pristine_ledger()
        if tuple(ledger["construction_order"]) != IN_SCOPE:
            raise ValueError("frozen ledger order differs")
        ledger["mutation_enabled"] = True
        ledger["release_commit"] = FREEZE_COMMIT
        ledger["release_manifest_sha256"] = MANIFEST_SHA256
        write_new_json(LEDGER_PATH, ledger)


def assert_attempt_permitted(family: str, number: int) -> None:
    ledger = read_json(LEDGER_PATH)
    if ledger.get("next_family") != family:
        raise ValueError(
            f"family is out of frozen order: expected {ledger.get('next_family')}, got {family}"
        )
    rows = [row for row in ledger["attempts"] if row.get("family_id") == family]
    if any(row.get("status") == "RUNNING" for row in ledger["attempts"]):
        raise ValueError("another constructor attempt is still marked RUNNING")
    if len(rows) + 1 != number or number > ATTEMPT_CAP:
        raise ValueError("attempt number differs from append-only ledger")
    if attempt_root(family, number).exists():
        raise FileExistsError(
            f"refusing to overwrite append-only attempt: {attempt_root(family, number)}"
        )


def materialize_attempt(family: str, number: int, binding: dict[str, Any]) -> dict[str, Any]:
    root = attempt_root(family, number)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite append-only attempt: {root}")
    workspace = root / "workspace"
    record = root / "record"
    for path in (
        workspace / "inputs/source",
        workspace / "repository",
        workspace / "tools",
        workspace / "components/neutral_target/app",
        workspace / "components/functional_target/app",
        workspace / ".scratch",
        record,
    ):
        path.mkdir(parents=True, exist_ok=True)
    write_new(workspace / "AGENTS.md", WORKSPACE_AGENTS.encode("utf-8"))
    write_new_json(workspace / "interface.json", adapter.interface_for_family(family))
    task_source = REPO_ROOT / binding["scientific_task"]
    source_source = REPO_ROOT / binding["source"]
    repository_source = REPO_ROOT / binding["public_repository"]
    copy_new(task_source, workspace / "inputs/task.json")
    copy_new(source_source, workspace / "inputs/source" / source_source.name)
    shutil.copytree(repository_source, workspace / "repository", dirs_exist_ok=True, symlinks=True)
    write_new(workspace / "tools/run_public.py", public_tool(family, binding))
    make_read_only(workspace / "inputs")
    make_read_only(workspace / "repository")
    make_read_only(workspace / "tools")
    (workspace / "AGENTS.md").chmod(0o444)
    (workspace / "interface.json").chmod(0o444)
    prompt = render_prompt(family, number)
    write_new(record / "prompt.txt", prompt)
    manifest = {
        "schema_version": "controlled-v3-operational-render-record/1",
        "construction_version": CONSTRUCTION_VERSION,
        "operational_release_id": OPERATIONAL_RELEASE_ID,
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "scientific_freeze_commit": FREEZE_COMMIT,
        "scientific_manifest_sha256": MANIFEST_SHA256,
        "family_id": family,
        "attempt": attempt_name(number),
        "frozen_order": IN_SCOPE.index(family) + 1,
        "rendered_at_utc": utc_now(),
        "construction_nonce": construction_nonce(family, number),
        "sampling_seed": None,
        "prior_attempt_feedback_present": False,
        "sealed_tests_present": False,
        "reference_states_present": False,
        "validator_present": False,
        "evaluated_outcomes_present": False,
        "human_judgments_present": False,
        "ceiling_risk_label_present": False,
        "synthetic_u_request_present": False,
        "patch_authorship_request_present": False,
        "prompt_sha256": sha256_bytes(prompt),
        "interface_sha256": sha256_file(workspace / "interface.json"),
        "bound_task_sha256": sha256_file(task_source),
        "bound_source_sha256": sha256_file(source_source),
        "bound_public_repository_snapshot": tree_snapshot(repository_source),
        "initial_workspace_snapshot": tree_snapshot(workspace),
    }
    write_new_json(record / "render_manifest.json", manifest)
    return manifest


def validate_attempt(family: str, candidate: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = validator.validate_candidate(
            candidate, family, expected_release_sha256=MANIFEST_SHA256
        )
        return {
            "completed": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "result": result,
            "exception": None,
        }
    except BaseException as error:
        return {
            "completed": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "result": None,
            "exception": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }


def adapt_attempt(family: str, components: Path, candidate: Path) -> dict[str, Any]:
    started = time.monotonic()
    try:
        report = adapter.build_candidate(components, candidate, family)
        return {
            "completed": True,
            "duration_seconds": round(time.monotonic() - started, 3),
            "report": report,
            "exception": None,
        }
    except BaseException as error:
        return {
            "completed": False,
            "duration_seconds": round(time.monotonic() - started, 3),
            "report": None,
            "exception": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }


def refusal_markers(record: Path) -> bool:
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (record / "events.jsonl", record / "final_message.txt")
        if path.is_file()
    ).lower()
    return any(
        marker in text
        for marker in (
            "i can\u2019t assist",
            "i can't assist",
            "cannot assist",
            "i must refuse",
            "unable to help with",
        )
    )


def classify(
    execution: dict[str, Any],
    adaptation: dict[str, Any],
    validation: dict[str, Any],
    record: Path,
) -> tuple[list[str], bool]:
    categories: list[str] = []
    telemetry = execution["telemetry"]
    infrastructure = False
    if execution["returncode"] != 0:
        categories.append("CONSTRUCTOR_PROCESS_ERROR")
        infrastructure = True
    if execution["timed_out"]:
        categories.append("CONSTRUCTOR_TIMEOUT")
        infrastructure = True
    if execution["tool_limit_exceeded"]:
        categories.append("TOOL_CALL_LIMIT_EXCEEDED")
    if execution["output_limit_exceeded"]:
        categories.append("OUTPUT_TOKEN_LIMIT_EXCEEDED")
    if not telemetry["terminal_event_present"]:
        categories.append("CONSTRUCTOR_TERMINAL_EVENT_MISSING")
        infrastructure = True
    if not adaptation["completed"]:
        if refusal_markers(record) or (
            telemetry["terminal_event_present"]
            and not infrastructure
            and not any((record.parent / "workspace/components").rglob("service.*"))
        ):
            categories.append("CONSTRUCTOR_REFUSAL")
        else:
            categories.append("CANDIDATE_COMPONENT_INTERFACE_ERROR")
    elif not validation["completed"]:
        categories.append("VALIDATOR_EXCEPTION")
    elif validation["result"].get("machine_valid") is not True:
        rows = validation["result"].get("matrix", {}).values()
        if any(
            isinstance(row, dict) and row.get("worker_status") != "COMPLETE" for row in rows
        ):
            categories.append("VALIDATOR_HARNESS_ERROR")
        else:
            categories.append("MACHINE_MATRIX_REJECT")
    machine_admitted = (
        adaptation["completed"]
        and validation["completed"]
        and validation["result"].get("machine_valid") is True
    )
    if machine_admitted:
        categories = []
    elif not categories:
        categories = ["UNCLASSIFIED_CONSTRUCTION_FAILURE"]
    return categories, machine_admitted


def candidate_digest(snapshot: dict[str, Any]) -> str:
    return sha256_bytes(canonical(snapshot.get("entries", [])))


def run_attempt(family: str, number: int) -> dict[str, Any]:
    gate = verify_protocol_gate()
    initialize_control(gate)
    assert_attempt_permitted(family, number)
    bindings = adapter.load_bindings()
    binding = bindings[family]
    root = attempt_root(family, number)
    render = materialize_attempt(family, number, binding)
    workspace = root / "workspace"
    record = root / "record"
    prompt = (record / "prompt.txt").read_bytes()
    if sha256_bytes(prompt) != render["prompt_sha256"]:
        raise ValueError("rendered prompt hash mismatch")
    controller = control.DisposableLedgerController(LEDGER_PATH)
    ledger_row = controller.begin(family, utc_now(), MANIFEST_SHA256)
    if ledger_row["attempt"] != number:
        raise ValueError("disposable ledger attempt number differs")
    codex = runtime.resolve_codex()
    observation = runtime.runtime_observation(codex)
    with tempfile.TemporaryDirectory(
        prefix=f"v3-{family.lower()}-{attempt_name(number)}-constructor-"
    ) as temporary:
        chroot = Path(temporary) / "root"
        runtime.initialize_chroot(chroot, codex)
        inside = runtime.codex_exec_arguments("/workspace/.scratch/final_message.txt")
        command = runtime.isolated_command(chroot, workspace, inside, codex=codex)
        write_new_json(
            record / "started.json",
            {
                "schema_version": "controlled-v3-operational-attempt-start/1",
                "construction_version": CONSTRUCTION_VERSION,
                "family_id": family,
                "attempt": attempt_name(number),
                "started_at_utc": ledger_row["started_at"],
                "ledger_row": ledger_row,
                "runtime": observation,
                "host_command": command,
                "inside_codex_command": ["codex", *inside],
                "python": sys.version,
                "platform": platform.platform(),
                "single_external_containment_boundary": True,
                "nested_bubblewrap": False,
                "nested_devpts": False,
            },
        )
        execution = runtime.execute_codex(
            command,
            workspace=workspace,
            prompt=prompt,
            events=record / "events.jsonl",
            stderr=record / "stderr.log",
            timeout_seconds=TIMEOUT_SECONDS,
            tool_call_limit=TOOL_CALL_LIMIT,
            maximum_output_tokens=MAXIMUM_OUTPUT_TOKENS,
        )
    final = workspace / ".scratch/final_message.txt"
    write_new(record / "final_message.txt", final.read_bytes() if final.is_file() else b"")
    component_snapshot = tree_snapshot(workspace / "components")
    write_new_json(record / "component_snapshot.json", component_snapshot)
    adaptation = adapt_attempt(
        family, workspace / "components", record / "derived_candidate"
    )
    write_new_json(record / "adaptation.json", adaptation)
    if adaptation["completed"]:
        validation_result = validate_attempt(family, record / "derived_candidate")
    else:
        validation_result = {
            "completed": False,
            "duration_seconds": 0.0,
            "result": None,
            "exception": None,
            "not_run_reason": "COMPONENT_INTERFACE_DID_NOT_ADAPT",
        }
    write_new_json(record / "validation.json", validation_result)
    candidate_snapshot = tree_snapshot(record / "derived_candidate")
    write_new_json(record / "candidate_snapshot.json", candidate_snapshot)
    workspace_snapshot = tree_snapshot(workspace)
    write_new_json(record / "workspace_final_snapshot.json", workspace_snapshot)
    categories, admitted = classify(execution, adaptation, validation_result, record)
    digest = candidate_digest(candidate_snapshot if adaptation["completed"] else component_snapshot)
    machine_result = (
        "MACHINE_VALID"
        if admitted
        else "INFRASTRUCTURE_ERROR"
        if any(
            category
            in {
                "CONSTRUCTOR_PROCESS_ERROR",
                "CONSTRUCTOR_TIMEOUT",
                "CONSTRUCTOR_TERMINAL_EVENT_MISSING",
                "VALIDATOR_EXCEPTION",
                "VALIDATOR_HARNESS_ERROR",
            }
            for category in categories
        )
        else "MACHINE_INVALID"
    )
    finished_ledger = controller.finish(family, number, machine_result, digest)
    outcome: dict[str, Any] = {
        "schema_version": "controlled-v3-operational-attempt-outcome/1",
        "construction_version": CONSTRUCTION_VERSION,
        "operational_release_id": OPERATIONAL_RELEASE_ID,
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "scientific_freeze_commit": FREEZE_COMMIT,
        "scientific_manifest_sha256": MANIFEST_SHA256,
        "family_id": family,
        "attempt": attempt_name(number),
        "completed_at_utc": utc_now(),
        "execution": execution,
        "adaptation_sha256": sha256_file(record / "adaptation.json"),
        "validation_sha256": sha256_file(record / "validation.json"),
        "candidate_sha256": digest,
        "failure_categories": categories,
        "machine_result": machine_result,
        "machine_admitted": admitted,
        "first_admissible_retention": True,
        "ledger_row": finished_ledger,
        "manual_repair_performed": False,
        "evaluated_agents_run": 0,
        "human_reviews_performed": 0,
        "accepted_hashes": None,
    }
    if admitted:
        result = validation_result["result"]
        outcome["accepted_hashes"] = {
            "candidate_sha256": digest,
            "state_tree_sha256": result["integrity"]["state_tree_sha256"],
            "feature_patch_sha256": result["integrity"]["feature_patch"]["sha256"],
            "security_patch_sha256": result["integrity"]["security_patch"]["sha256"],
        }
    write_new_json(record / "outcome.json", outcome)
    write_new_json(record / "ledger_after_attempt.json", read_json(LEDGER_PATH))
    update_progress()
    return outcome


def existing_outcomes(family: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number in range(1, ATTEMPT_CAP + 1):
        root = attempt_root(family, number)
        outcome = root / "record/outcome.json"
        if outcome.is_file():
            rows.append(read_json(outcome))
        elif root.exists():
            raise RuntimeError(f"incomplete append-only attempt requires audit: {root}")
        else:
            break
    return rows


def next_attempt_number(family: str) -> int | None:
    rows = existing_outcomes(family)
    if any(row.get("machine_admitted") is True for row in rows) or len(rows) >= ATTEMPT_CAP:
        return None
    return len(rows) + 1


def family_status(family: str) -> dict[str, Any]:
    outcomes = existing_outcomes(family)
    accepted = next((row for row in outcomes if row.get("machine_admitted") is True), None)
    status = (
        "MACHINE_ADMITTED"
        if accepted
        else "CONSTRUCTION_EXHAUSTED"
        if len(outcomes) == ATTEMPT_CAP
        else "PENDING"
    )
    return {
        "family_id": family,
        "ceiling_risk": next(label for label, members in RISK_LABELS.items() if family in members),
        "attempt_count": len(outcomes),
        "status": status,
        "accepted_attempt": accepted.get("attempt") if accepted else None,
        "accepted_candidate_hashes": accepted.get("accepted_hashes") if accepted else None,
        "attempts": [
            {
                "attempt": row["attempt"],
                "machine_result": row["machine_result"],
                "machine_admitted": row["machine_admitted"],
                "candidate_sha256": row["candidate_sha256"],
                "failure_categories": row["failure_categories"],
            }
            for row in outcomes
        ],
    }


def run_family(family: str) -> dict[str, Any]:
    if family not in IN_SCOPE:
        raise ValueError(f"family is excluded or unknown: {family}")
    while (number := next_attempt_number(family)) is not None:
        outcome = run_attempt(family, number)
        if outcome["machine_admitted"]:
            break
    return family_status(family)


def report() -> dict[str, Any]:
    families = [family_status(family) for family in IN_SCOPE]
    categories = Counter(
        category
        for family in families
        for attempt in family["attempts"]
        for category in attempt["failure_categories"]
    )
    initial_production = (
        read_json(CONTROL_PATH)["production_ledger_initial_sha256"]
        if CONTROL_PATH.is_file()
        else sha256_file(PRODUCTION_LEDGER_PATH)
    )
    science = preparation.verify_science()
    return {
        "schema_version": "controlled-v3-operational-construction-report/1",
        "construction_version": CONSTRUCTION_VERSION,
        "operational_release_id": OPERATIONAL_RELEASE_ID,
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "scientific_freeze_commit": FREEZE_COMMIT,
        "scientific_manifest_sha256": MANIFEST_SHA256,
        "family_order": list(IN_SCOPE),
        "families": families,
        "excluded": [
            {
                "family_id": family,
                "attempt_count": 0,
                "status": "PRE_CONSTRUCTION_EXCLUDED_ZERO_ATTEMPTS",
            }
            for family in EXCLUDED
        ],
        "resolved_count": sum(row["status"] != "PENDING" for row in families),
        "machine_admitted_count": sum(row["status"] == "MACHINE_ADMITTED" for row in families),
        "construction_exhausted_count": sum(
            row["status"] == "CONSTRUCTION_EXHAUSTED" for row in families
        ),
        "pending_count": sum(row["status"] == "PENDING" for row in families),
        "total_constructor_attempts": sum(row["attempt_count"] for row in families),
        "constructor_failure_categories": dict(sorted(categories.items())),
        "accepted_candidate_hashes": {
            row["family_id"]: row["accepted_candidate_hashes"]
            for row in families
            if row["accepted_candidate_hashes"] is not None
        },
        "frozen_scientific_artifacts_unchanged": (
            science["status"] == "PASS"
            and sha256_file(PRODUCTION_LEDGER_PATH) == initial_production
        ),
        "production_ledger_sha256": sha256_file(PRODUCTION_LEDGER_PATH),
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
    }


def update_progress() -> dict[str, Any]:
    value = report()
    value["reported_at_utc"] = utc_now()
    replace_json(PROGRESS_PATH, value)
    return value


def finalize_report() -> dict[str, Any]:
    value = report()
    if value["pending_count"]:
        raise ValueError("cannot finalize while construction families remain pending")
    value["completed_at_utc"] = utc_now()
    if FINAL_REPORT_PATH.exists():
        if read_json(FINAL_REPORT_PATH) != value:
            raise FileExistsError("refusing to overwrite a different final report")
    else:
        write_new_json(FINAL_REPORT_PATH, value)
    update_progress()
    return value


def run_all() -> dict[str, Any]:
    verify_protocol_gate()
    for family in IN_SCOPE:
        run_family(family)
    return finalize_report()


def status_without_starting() -> dict[str, Any]:
    if not RESULT_ROOT.exists():
        return {
            "construction_version": CONSTRUCTION_VERSION,
            "status": "NOT_STARTED",
            "total_constructor_attempts": 0,
            "pending_count": len(IN_SCOPE),
            "evaluated_agent_outcomes": 0,
            "actual_v3_human_reviews": 0,
        }
    return report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--attempt", choices=IN_SCOPE)
    parser.add_argument("--family", choices=IN_SCOPE)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    selected = sum(bool(value) for value in (args.verify, args.status, args.attempt, args.family, args.all))
    if selected != 1:
        parser.error("choose exactly one action")
    if args.verify:
        gate = verify_protocol_gate()
        result: object = {
            "status": "READY_NOT_STARTED",
            "construction_version": CONSTRUCTION_VERSION,
            "gate": gate["dummy_gate"],
            "science": gate["science"],
            "runtime": runtime.runtime_observation(),
            "result_root_exists": RESULT_ROOT.exists(),
        }
    elif args.status:
        result = status_without_starting()
    elif args.attempt:
        number = next_attempt_number(args.attempt)
        result = family_status(args.attempt) if number is None else run_attempt(args.attempt, number)
    elif args.family:
        result = run_family(args.family)
    else:
        result = run_all()
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True, default=repr))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

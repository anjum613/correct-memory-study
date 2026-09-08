from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from cmpilot.environment_fingerprint import (
    MATCH_CLASSIFICATION,
    MISMATCH_CLASSIFICATION,
    SCHEMA_VERSION,
    load_inventory_records,
    render_load_gate_block,
    write_fingerprint_artifacts,
)


ROOT = Path(__file__).parents[1]
TOOL = ROOT / "scripts" / "environment_fingerprint.py"
FIXTURES = ROOT / "tests" / "fixtures"
LOGIN_FIXTURE = FIXTURES / "job_25033_packages_login.json"
BATCH_FIXTURE = FIXTURES / "job_25033_packages_batch.json"


def _write_runner(
    path: Path,
    artifact_dir: Path,
    expected_record: Path,
    records_path: Path,
) -> None:
    block = render_load_gate_block(
        python_path=Path(sys.executable),
        tool_path=TOOL,
        expected_record=expected_record,
        records_path=records_path,
    )
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"ARTIFACT_DIR={shlex.quote(str(artifact_dir))}\n"
        'mkdir -p "$ARTIFACT_DIR"\n'
        + block,
        encoding="utf-8",
        newline="\n",
    )
    path.chmod(0o700)


def _run(path: Path, locale_values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key == "LANG" or key.startswith("LC_"):
            environment.pop(key)
    environment.update(locale_values)
    return subprocess.run(
        ["/usr/bin/bash", str(path)],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_generated_load_gate_uses_v2_and_locale_fallback_without_sort(
    tmp_path: Path,
) -> None:
    block = render_load_gate_block(
        python_path=Path(sys.executable),
        tool_path=TOOL,
        expected_record=tmp_path / "expected.json",
    )

    assert "set -euo pipefail" in block
    assert SCHEMA_VERSION in block
    assert "LC_ALL=C.UTF-8" in block
    assert "LANG=C.UTF-8" in block
    assert "LC_ALL=C" in block
    assert "LANG=C" in block
    assert "environment-inventory-v2.json" in block
    assert "environment-fingerprint-v2.json" in block
    assert "environment-fingerprint-classification.json" in block
    assert "sort" not in block
    assert "cmp -s" not in block


def test_load_gate_passes_for_job_25033_locale_ordering_difference(
    tmp_path: Path,
) -> None:
    expected_inventory = tmp_path / "expected-inventory.json"
    expected_record = tmp_path / "expected-record.json"
    write_fingerprint_artifacts(
        expected_inventory,
        expected_record,
        records=load_inventory_records(LOGIN_FIXTURE),
    )
    artifact_dir = tmp_path / "gate-artifacts"
    runner = tmp_path / "gate.sh"
    _write_runner(runner, artifact_dir, expected_record, BATCH_FIXTURE)

    result = _run(runner, {"LANG": "C", "LC_ALL": "C"})
    classification = json.loads(
        (artifact_dir / "environment-fingerprint-classification.json").read_text(
            encoding="utf-8"
        )
    )

    assert result.returncode == 0, result.stderr
    assert classification["label"] == MATCH_CLASSIFICATION
    assert classification["schema"] == SCHEMA_VERSION
    assert classification["match"] is True


def test_load_gate_fails_closed_for_genuine_v2_difference(tmp_path: Path) -> None:
    expected_inventory = tmp_path / "expected-inventory.json"
    expected_record = tmp_path / "expected-record.json"
    login_records = load_inventory_records(LOGIN_FIXTURE)
    write_fingerprint_artifacts(
        expected_inventory, expected_record, records=login_records
    )
    changed_records = [dict(record) for record in load_inventory_records(BATCH_FIXTURE)]
    changed_records[0]["version"] += ".changed"
    changed_path = tmp_path / "changed-records.json"
    changed_path.write_text(
        json.dumps({"records": changed_records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    artifact_dir = tmp_path / "gate-artifacts"
    runner = tmp_path / "gate.sh"
    _write_runner(runner, artifact_dir, expected_record, changed_path)

    result = _run(runner, {"LANG": "en_US.UTF-8"})
    classification = json.loads(
        (artifact_dir / "environment-fingerprint-classification.json").read_text(
            encoding="utf-8"
        )
    )

    assert result.returncode == 75
    assert MISMATCH_CLASSIFICATION in result.stderr
    assert classification["label"] == MISMATCH_CLASSIFICATION
    assert classification["schema"] == SCHEMA_VERSION
    assert classification["match"] is False
    assert classification["expected_sha256"] != classification["actual_sha256"]


def test_fingerprint_cli_capture_and_compare_use_the_same_implementation(
    tmp_path: Path,
) -> None:
    first_inventory = tmp_path / "first-inventory.json"
    first_record = tmp_path / "first-record.json"
    second_inventory = tmp_path / "second-inventory.json"
    second_record = tmp_path / "second-record.json"
    classification = tmp_path / "classification.json"

    for inventory, record, fixture, locale_name in (
        (first_inventory, first_record, LOGIN_FIXTURE, "en_US.UTF-8"),
        (second_inventory, second_record, BATCH_FIXTURE, "C"),
    ):
        environment = os.environ.copy()
        environment.update({"LANG": locale_name, "LC_ALL": locale_name})
        subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "capture",
                "--inventory",
                str(inventory),
                "--record",
                str(record),
                "--records",
                str(fixture),
            ],
            cwd=ROOT,
            env=environment,
            check=True,
        )

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "compare",
            "--expected",
            str(first_record),
            "--actual",
            str(second_record),
            "--classification",
            str(classification),
        ],
        cwd=ROOT,
        check=False,
    )

    assert result.returncode == 0
    assert json.loads(classification.read_text(encoding="utf-8"))["match"] is True

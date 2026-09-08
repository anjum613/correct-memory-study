from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmpilot.source_integrity import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    SourceIntegrityError,
    generate_source_integrity,
    validate_source_integrity_record,
)


ROOT = Path(__file__).parents[1]


def _snapshot(path: Path, *, digest: str = "digest", root_mode: str = "0555") -> None:
    path.write_text(
        json.dumps(
            {
                "content_digest": digest,
                "mode_inventory": [
                    {"path": "strange", "mode": "0444"},
                ],
                "root_mode": root_mode,
            }
        ),
        encoding="utf-8",
    )


def test_source_integrity_json_round_trips_arbitrary_runtime_values(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "initial 'single' \"double\" \\ path.json"
    final = tmp_path / "final;$(shell)\nUnicode-λ.json"
    _snapshot(initial)
    _snapshot(final)
    special_values = {
        "single": "'",
        "double": '"',
        "backslash": "\\",
        "newline": "first\nsecond",
        "shell": "; $() `ticks` & | < >",
        "unicode": "λ雪",
        "long_path": "/owned/" + "segment/" * 1000,
    }
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "source-integrity.json"
    input_path.write_text(
        json.dumps(
            {
                "schema": INPUT_SCHEMA,
                "comparisons": [
                    {
                        "name": "source 'fixture'\nλ",
                        "initial_path": str(initial),
                        "final_path": str(final),
                        "expected_root_mode": "0555",
                    }
                ],
                "findings": [special_values],
                "metadata": special_values,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = generate_source_integrity(input_path, output_path)
    parsed = json.loads(output_path.read_text(encoding="utf-8"))

    assert result == parsed
    assert parsed["schema"] == OUTPUT_SCHEMA
    assert parsed["pass"] is True
    assert parsed["metadata"] == special_values
    assert parsed["findings"] == [special_values]
    assert not list(tmp_path.glob(".source-integrity.json.*.tmp"))


def test_job_25642_unterminated_source_is_a_fixed_regression_fixture() -> None:
    broken = (
        ROOT / "tests" / "fixtures" / "job_25642_source_integrity_broken.py.txt"
    ).read_text(encoding="utf-8")

    with pytest.raises(SyntaxError, match="unterminated string literal"):
        compile(broken, "job-25642-generated-source.py", "exec")
    helper_source = (
        ROOT / "src" / "cmpilot" / "source_integrity.py"
    ).read_text(encoding="utf-8")
    assert "json.dump(value" in helper_source
    assert "os.replace(temporary, path)" in helper_source
    assert "eval(" not in helper_source


def test_source_integrity_schema_rejects_malformed_generated_json(
    tmp_path: Path,
) -> None:
    malformed = {"schema": OUTPUT_SCHEMA, "pass": True}

    with pytest.raises(SourceIntegrityError, match="checks"):
        validate_source_integrity_record(malformed)

    output = tmp_path / "source-integrity.json"
    output.write_text("{not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(output.read_text(encoding="utf-8"))


def test_source_integrity_failure_is_structured_and_still_written(
    tmp_path: Path,
) -> None:
    initial = tmp_path / "initial.json"
    final = tmp_path / "final.json"
    _snapshot(initial, digest="before")
    _snapshot(final, digest="after", root_mode="0700")
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "source-integrity.json"
    input_path.write_text(
        json.dumps(
            {
                "schema": INPUT_SCHEMA,
                "comparisons": [
                    {
                        "name": "source-fixture",
                        "initial_path": str(initial),
                        "final_path": str(final),
                        "expected_root_mode": "0555",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = generate_source_integrity(input_path, output_path)

    assert result["pass"] is False
    assert result["checks"]["source-fixture"] == {
        "content_digest_unchanged": False,
        "modes_unchanged": True,
        "root_mode_matches_expected": False,
    }
    assert validate_source_integrity_record(
        json.loads(output_path.read_text(encoding="utf-8"))
    ) == result

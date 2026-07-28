from __future__ import annotations

from cmpilot.artifact_logger import create_run_directory, write_json, write_text


def test_artifact_directories_have_unique_run_ids(tmp_path) -> None:
    first_path, first_id = create_run_directory(tmp_path)
    second_path, second_id = create_run_directory(tmp_path)

    assert first_path.is_dir()
    assert second_path.is_dir()
    assert first_id != second_id
    assert first_path != second_path


def test_artifact_writes_redact_secrets(tmp_path) -> None:
    text_path = tmp_path / "command.txt"
    json_path = tmp_path / "config.json"

    write_text(text_path, "OPENAI_API_KEY=test-only-value TOKEN: another-test-value")
    write_json(json_path, {"api_key": "test-only-value", "nested": {"password": "test-password-value"}})

    assert "test-only-value" not in text_path.read_text()
    assert "another-test-value" not in text_path.read_text()
    assert "test-only-value" not in json_path.read_text()
    assert "test-password-value" not in json_path.read_text()

from __future__ import annotations

from cmpilot.artifact_logger import create_profiled_run_directory, create_run_directory, write_json, write_text


def test_artifact_directories_have_unique_run_ids(tmp_path) -> None:
    first_path, first_id = create_run_directory(tmp_path)
    second_path, second_id = create_run_directory(tmp_path)

    assert first_path.is_dir()
    assert second_path.is_dir()
    assert first_id != second_id
    assert first_path != second_path


def test_profiled_run_id_contains_exact_model_identity(tmp_path) -> None:
    path, run_id = create_profiled_run_directory(tmp_path, "devstral-small-2507-bd165ab26ceb")

    assert path.name == run_id
    assert run_id.startswith("smoke-devstral-small-2507-bd165ab26ceb-")


def test_artifact_writes_redact_secrets(tmp_path) -> None:
    text_path = tmp_path / "command.txt"
    json_path = tmp_path / "config.json"

    write_text(text_path, "OPENAI_API_KEY=test-only-value TOKEN: another-test-value")
    write_json(json_path, {"api_key": "test-only-value", "nested": {"password": "test-password-value"}})

    assert "test-only-value" not in text_path.read_text()
    assert "another-test-value" not in text_path.read_text()
    assert "test-only-value" not in json_path.read_text()
    assert "test-password-value" not in json_path.read_text()


def test_public_tokenizer_attestation_is_not_mistaken_for_a_secret(tmp_path) -> None:
    path = tmp_path / "model.json"

    write_json(
        path,
        {
            "tokenizer_id": "mistralai/Devstral-Small-2507",
            "tokenizer_revision": "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39",
            "access_token": "must-remain-secret",
        },
    )

    contents = path.read_text()
    assert "mistralai/Devstral-Small-2507" in contents
    assert "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39" in contents
    assert "must-remain-secret" not in contents


def test_tokenizer_named_field_still_redacts_a_non_metadata_secret(tmp_path) -> None:
    path = tmp_path / "unsafe.json"

    write_json(path, {"tokenizer_revision": "secret-value-that-is-not-a-commit"})

    assert "secret-value-that-is-not-a-commit" not in path.read_text()

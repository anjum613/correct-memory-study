from __future__ import annotations

from pathlib import Path

from cmpilot.devstral_native_mini_swe_adapter import (
    write_devstral_native_production_adapter,
)
from cmpilot.qwen3_final13 import qwen3_cells, validate_model_profile
from scripts.run_devstral_final13 import (
    DEFAULT_AGENT_DEPENDENCIES,
    DEFAULT_MINI_PYTHON,
    MODEL_ID,
    MODEL_REVISION,
    SERVED_MODEL_NAME,
    SOURCE_MODEL_KEY,
    TEKKEN_SHA256,
)


ROOT = Path(__file__).parents[1]


def test_devstral_projects_the_complete_frozen_arm() -> None:
    cells = qwen3_cells(
        ROOT,
        source_model_key=SOURCE_MODEL_KEY,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
    )

    assert len(cells) == 104
    assert len({cell.family_id for cell in cells}) == 13
    assert {cell.condition for cell in cells} == {
        "NO_MEMORY",
        "SOURCE_CORRECT_MEMORY",
        "MATCHED_IRRELEVANT_MEMORY",
        "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
    }
    for family_id in {cell.family_id for cell in cells}:
        assert len([cell for cell in cells if cell.family_id == family_id]) == 8


def test_devstral_runpod_profile_binds_official_native_runtime() -> None:
    result = validate_model_profile(
        ROOT,
        model_profile_path=Path(
            "configs/models/devstral-small-2507-recommended-runpod.json"
        ),
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        served_model_name=SERVED_MODEL_NAME,
        tokenizer_json_sha256=TEKKEN_SHA256,
        tokenizer_config_sha256=TEKKEN_SHA256,
        context_limit=32768,
        completion_limit=512,
        temperature=0.15,
        native_tool_calls=True,
        tokenizer_kind="mistral",
        tokenizer_tekken_sha256=TEKKEN_SHA256,
        quantization=None,
        dtype="bfloat16",
        tool_call_parser="mistral",
    )

    assert result["status"] == "PASS"


def test_devstral_native_adapter_wraps_shared_policy_runtime(tmp_path: Path) -> None:
    adapter = tmp_path / "mini_swe_adapter.py"
    record = write_devstral_native_production_adapter(adapter)

    assert adapter.is_file()
    assert (tmp_path / "cmpilot_policy_adapter_runtime.py").is_file()
    assert (tmp_path / "cmpilot_devstral_native_serialization.py").is_file()
    assert record["frozen_adapter_sha256"]
    assert record["serialization_adapter_sha256"]


def test_devstral_start_script_uses_documented_mistral_flags() -> None:
    source = (ROOT / "scripts/start_devstral_small_2507_runpod.sh").read_text()

    for option in (
        "--tokenizer-mode mistral",
        "--config-format mistral",
        "--load-format mistral",
        "--tool-call-parser mistral",
        "--enable-auto-tool-choice",
        "--tensor-parallel-size 2",
        "--max-model-len 32768",
    ):
        assert option in source


def test_devstral_uses_proven_agent_and_isolated_native_dependencies() -> None:
    assert DEFAULT_MINI_PYTHON.endswith("/mini-swe-agent-smoke/bin/python")
    assert DEFAULT_AGENT_DEPENDENCIES.endswith("/devstral-small-2507-deps-v1")

    wrapper = (ROOT / "scripts/run_devstral_final13_hpc.sh").read_text()
    assert "devstral-small-2507-agent-v1" not in wrapper
    assert "--agent-dependency-path" in wrapper

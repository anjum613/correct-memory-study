from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from cmpilot.mini_swe_adapter import (
    RUNTIME_MODEL_MODULE,
    RUNTIME_SOURCE_MANIFEST_MODULE,
    RUNTIME_TRANSPORT_MODULE,
    write_adapter,
)
from cmpilot.multiturn_preflight import (
    PASS_CLASSIFICATION,
    MultiturnPreflightConfig,
    run_multiturn_preflight,
)


ROOT = Path(__file__).parents[1]
DEFAULT_MINI_PY = Path("/home/s224049759/environments/mini-swe-agent-smoke/bin/python")


def _mini_python() -> Path:
    return Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))


def _run_mini(script: str, *, python_path: Path, home: Path) -> subprocess.CompletedProcess[str]:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    environment = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "MSWEA_SILENT_STARTUP": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(python_path),
    }
    return subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )


def test_direct_model_loads_through_mini_full_import_path(tmp_path: Path) -> None:
    write_adapter(tmp_path / "mini_swe_adapter.py")
    result = _run_mini(
        """
        from minisweagent.models import get_model_class
        from cmpilot_vllm_text_model import VllmTextModel, VllmTextModelConfig

        model_class = get_model_class(
            "Qwen/Qwen2.5-Coder-1.5B-Instruct",
            "cmpilot_vllm_text_model.VllmTextModel",
        )
        assert model_class is VllmTextModel
        model = model_class(
            model_name="Qwen/Qwen2.5-Coder-1.5B-Instruct",
            base_url="http://127.0.0.1:9/v1",
            temperature=0.0,
            max_tokens=32,
        )
        required = {
            "query",
            "format_message",
            "format_observation_messages",
            "get_template_vars",
            "serialize",
        }
        assert all(callable(getattr(model, name, None)) for name in required)
        assert VllmTextModelConfig(**model.config.model_dump()).model_name.startswith("Qwen/")
        print(model.serialize()["info"]["config"]["model_type"])
        """,
        python_path=tmp_path,
        home=tmp_path / "home",
    )

    assert result.returncode == 0, result.stderr
    assert "cmpilot_vllm_text_model.VllmTextModel" in result.stdout
    assert (tmp_path / RUNTIME_MODEL_MODULE).is_file()
    assert (tmp_path / RUNTIME_TRANSPORT_MODULE).is_file()
    assert (tmp_path / RUNTIME_SOURCE_MANIFEST_MODULE).is_file()


def test_installed_mini_swe_source_manifest_is_unchanged(tmp_path: Path) -> None:
    result = _run_mini(
        """
        import json
        from cmpilot.integrations.miniswe.source_manifest import (
            require_installed_sources_unchanged,
        )

        manifest = require_installed_sources_unchanged()
        print(json.dumps(manifest, sort_keys=True))
        """,
        python_path=ROOT / "src",
        home=tmp_path / "home",
    )

    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout)
    assert manifest["installed_version"] == "2.4.6"
    assert manifest["all_match"] is True
    assert len(manifest["sources"]) == 9
    assert all(record["matches"] for record in manifest["sources"].values())


def test_deterministic_multiturn_preflight_runs_exact_adapter(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    artifacts = tmp_path / "artifacts"

    exit_code = run_multiturn_preflight(
        MultiturnPreflightConfig(
            mini_python=str(mini_python),
            artifact_dir=artifacts,
            timeout_seconds=60,
        )
    )

    result = json.loads((artifacts / "result.json").read_text(encoding="utf-8"))
    requests = [
        json.loads(line)
        for line in (artifacts / "mock-requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    transport = [
        json.loads(line)
        for line in (artifacts / "agent-run" / "model-transport.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    config = json.loads(
        (artifacts / "agent-run" / "agent-config.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert result["classification"] == PASS_CLASSIFICATION
    assert result["mock_request_count"] == 3
    assert result["model_request_count"] == 3
    assert result["repository_command_count"] == 3
    assert result["patch_size_bytes"] == 0
    assert result["usage"] == {
        "prompt_tokens": 306,
        "completion_tokens": 66,
        "total_tokens": 372,
    }
    assert all(record["accepted"] for record in requests)
    assert all(record["validation_errors"] == [] for record in requests)
    assert "provider_specific_fields" not in json.dumps(
        requests[1]["request"]["messages"], sort_keys=True
    )
    assert '"extra"' not in json.dumps(
        requests[1]["request"]["messages"], sort_keys=True
    )
    assert transport[0]["response"]["choices"][0]["message"][
        "provider_specific_fields"
    ] == {"mock_transport_metadata": 1}
    assert len({record["request_sha256"] for record in transport}) == 3
    assert all(record["status_code"] == 200 for record in transport)
    assert config["model"]["model_class"] == "cmpilot_vllm_text_model.VllmTextModel"
    assert "model_kwargs" not in config["model"]
    assert all(result["checks"].values())

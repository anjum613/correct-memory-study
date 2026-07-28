from __future__ import annotations

from unittest.mock import patch

from cmpilot import doctor
from cmpilot.vllm_client import ModelProbe


def test_collect_report_checks_the_models_endpoint_and_keeps_diagnostic() -> None:
    probe_result = ModelProbe(
        endpoint="http://127.0.0.1:8000/v1/models",
        ok=True,
        diagnostic="endpoint responded",
        status_code=200,
        models=("smoke-model",),
    )
    with (
        patch.object(doctor.platform, "system", return_value="Linux"),
        patch.object(doctor.sys, "version_info", (3, 11, 9, "final", 0)),
        patch.object(doctor, "command_is_available", return_value=True),
        patch.object(doctor, "gpu_is_available", return_value=True),
        patch.object(doctor, "probe_models", return_value=probe_result) as probe,
    ):
        report = doctor.collect_report({"VLLM_BASE_URL": "http://127.0.0.1:8000/v1"})

    assert report["vllm_endpoint_responds"] is True
    assert report["vllm_diagnostic"] == "endpoint responded"
    probe.assert_called_once_with("http://127.0.0.1:8000/v1", timeout=2)


def test_collect_report_does_not_probe_when_vllm_is_unconfigured() -> None:
    with (
        patch.object(doctor, "command_is_available", return_value=False),
        patch.object(doctor, "gpu_is_available", return_value=False),
        patch.object(doctor, "probe_models") as probe,
    ):
        report = doctor.collect_report({})

    assert report["vllm_base_url_configured"] is False
    assert report["vllm_endpoint_responds"] is None
    assert report["vllm_diagnostic"] is None
    probe.assert_not_called()


def test_render_report_does_not_include_the_configured_endpoint() -> None:
    output = doctor.render_report(
        {
            "python": "3.11.9",
            "operating_system": "Linux",
            "git_available": True,
            "singularity_available": False,
            "nvidia_gpu_available": False,
            "vllm_base_url_configured": True,
            "vllm_endpoint_responds": False,
            "vllm_diagnostic": "connection refused",
        }
    )

    assert "VLLM_BASE_URL configured: true" in output
    assert "Configured vLLM endpoint responds: false" in output
    assert "vLLM diagnostic: connection refused" in output
    assert "http://" not in output

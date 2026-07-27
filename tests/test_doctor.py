from __future__ import annotations

from unittest.mock import Mock, patch


def test_collect_report_checks_local_tools_and_a_configured_endpoint() -> None:
    from cmpilot import doctor

    with (
        patch.object(doctor.platform, "system", return_value="Linux"),
        patch.object(doctor.sys, "version_info", (3, 11, 9, "final", 0)),
        patch.object(
            doctor.shutil,
            "which",
            side_effect=lambda command: f"/usr/bin/{command}",
        ),
        patch.object(doctor, "gpu_is_available", return_value=True),
        patch.object(doctor, "vllm_endpoint_responds", return_value=True) as probe,
    ):
        report = doctor.collect_report({"VLLM_BASE_URL": "http://vllm.example"})

    assert report == {
        "python": "3.11.9",
        "operating_system": "Linux",
        "git_available": True,
        "singularity_available": True,
        "nvidia_gpu_available": True,
        "vllm_base_url_configured": True,
        "vllm_endpoint_responds": True,
    }
    probe.assert_called_once_with("http://vllm.example")


def test_collect_report_does_not_probe_when_vllm_is_unconfigured() -> None:
    from cmpilot import doctor

    with (
        patch.object(doctor, "command_is_available", return_value=False),
        patch.object(doctor, "gpu_is_available", return_value=False),
        patch.object(doctor, "vllm_endpoint_responds", new=Mock()) as probe,
    ):
        report = doctor.collect_report({})

    assert report["vllm_base_url_configured"] is False
    assert report["vllm_endpoint_responds"] is None
    probe.assert_not_called()


def test_render_report_does_not_include_the_configured_endpoint() -> None:
    from cmpilot.doctor import render_report

    output = render_report(
        {
            "python": "3.11.9",
            "operating_system": "Linux",
            "git_available": True,
            "singularity_available": False,
            "nvidia_gpu_available": False,
            "vllm_base_url_configured": True,
            "vllm_endpoint_responds": True,
        }
    )

    assert "VLLM_BASE_URL configured: true" in output
    assert "Configured vLLM endpoint responds: true" in output
    assert "http://" not in output

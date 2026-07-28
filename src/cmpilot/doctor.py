"""Offline-friendly environment checks for the initial scaffold."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping
from typing import TypedDict
from .vllm_client import probe_models


class DoctorReport(TypedDict):
    python: str
    operating_system: str
    git_available: bool
    singularity_available: bool
    nvidia_gpu_available: bool
    vllm_base_url_configured: bool
    vllm_endpoint_responds: bool | None
    vllm_diagnostic: str | None


def command_is_available(command: str) -> bool:
    """Return whether a command can be found on PATH."""
    return shutil.which(command) is not None


def gpu_is_available() -> bool:
    """Return whether nvidia-smi is available and reports successfully."""
    if not command_is_available("nvidia-smi"):
        return False

    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def vllm_endpoint_responds(base_url: str) -> bool:
    """Compatibility wrapper for the detailed models-endpoint probe."""
    return probe_models(base_url, timeout=2).ok


def collect_report(environment: Mapping[str, str] | None = None) -> DoctorReport:
    """Collect local checks and, only when configured, probe vLLM."""
    active_environment = os.environ if environment is None else environment
    base_url = active_environment.get("VLLM_BASE_URL", "").strip()
    configured = bool(base_url)

    probe = probe_models(base_url, timeout=2) if configured else None
    return {
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "operating_system": platform.system(),
        "git_available": command_is_available("git"),
        "singularity_available": command_is_available("singularity"),
        "nvidia_gpu_available": gpu_is_available(),
        "vllm_base_url_configured": configured,
        "vllm_endpoint_responds": probe.ok if probe else None,
        "vllm_diagnostic": probe.diagnostic if probe else None,
    }


def render_report(report: DoctorReport) -> str:
    """Format a report without exposing the configured endpoint URL."""
    endpoint_status = (
        "not checked" if report["vllm_endpoint_responds"] is None else str(report["vllm_endpoint_responds"]).lower()
    )
    return "\n".join(
        [
            f"Python version: {report['python']}",
            f"Operating system: {report['operating_system']}",
            f"Git available: {str(report['git_available']).lower()}",
            f"Singularity available: {str(report['singularity_available']).lower()}",
            f"NVIDIA GPU available: {str(report['nvidia_gpu_available']).lower()}",
            f"VLLM_BASE_URL configured: {str(report['vllm_base_url_configured']).lower()}",
            f"Configured vLLM endpoint responds: {endpoint_status}",
            f"vLLM diagnostic: {report['vllm_diagnostic'] or 'not checked'}",
        ]
    )

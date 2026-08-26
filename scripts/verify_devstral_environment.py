#!/usr/bin/env python3
"""CPU/tokenizer/CUDA preflight for the isolated Devstral runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import platform
import subprocess
import sys

from cmpilot.model_profiles import load_model_profile
from packaging.version import Version


EXPECTED_PYTHON = "3.11.11"
EXPECTED_PACKAGES = {
    "huggingface-hub": "0.33.4",
    "mistral-common": "1.8.4",
    "outlines-core": "0.2.10",
    "packaging": "25.0",
    "pip": "25.1.1",
    "tokenizers": "0.21.2",
    "torch": "2.7.1",
    "torchaudio": "2.7.1",
    "torchvision": "0.22.1",
    "transformers": "4.53.2",
    "vllm": "0.10.0",
    "xgrammar": "0.1.21",
}


def render_official_template() -> dict[str, object]:
    """Render but never submit a native Bash-tool request with the pinned tokenizer."""
    from mistral_common.protocol.instruct.messages import SystemMessage, UserMessage
    from mistral_common.protocol.instruct.request import ChatCompletionRequest
    from mistral_common.protocol.instruct.tool_calls import Function, Tool
    from mistral_common.tokens.tokenizers.mistral import MistralTokenizer

    profile = load_model_profile("devstral-small-2507")
    tokenizer = MistralTokenizer.from_hf_hub(
        profile.tokenizer_id,
        revision=profile.tokenizer_revision,
        local_files_only=True,
    )
    request = ChatCompletionRequest(
        messages=[
            SystemMessage(content="serialization preflight only"),
            UserMessage(content="inspect the working repository"),
        ],
        tools=[
            Tool(
                function=Function(
                    name="bash",
                    description="Execute a bash command",
                    parameters={
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                )
            )
        ],
    )
    token_ids = tokenizer.encode_chat_completion(request).tokens
    digest = hashlib.sha256(json.dumps(token_ids, separators=(",", ":")).encode()).hexdigest()
    return {
        "token_count": len(token_ids),
        "rendered_token_ids_sha256": digest,
        "tokenizer_id": profile.tokenizer_id,
        "tokenizer_revision": profile.tokenizer_revision,
        "tool_name": "bash",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-cuda", action="store_true")
    parser.add_argument("--expected-gpus", type=int, default=0)
    arguments = parser.parse_args()

    found_python = platform.python_version()
    found_packages = {name: metadata.version(name) for name in EXPECTED_PACKAGES}
    mismatches = {
        name: {"expected": expected, "found": found_packages[name]}
        for name, expected in EXPECTED_PACKAGES.items()
        if Version(found_packages[name]).base_version != expected
    }
    if found_python != EXPECTED_PYTHON:
        mismatches["python"] = {"expected": EXPECTED_PYTHON, "found": found_python}

    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    import torch

    cuda_available = torch.cuda.is_available()
    gpu_names = [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())] if cuda_available else []
    if torch.version.cuda != "12.8":
        mismatches["torch_cuda_runtime"] = {"expected": "12.8", "found": torch.version.cuda}
    report = {
        "python": found_python,
        "packages": found_packages,
        "package_mismatches": mismatches,
        "pip_check_exit_code": pip_check.returncode,
        "pip_check_output": (pip_check.stdout + pip_check.stderr).strip(),
        "torch_cuda_runtime": torch.version.cuda,
        "cuda_available": cuda_available,
        "gpu_names": gpu_names,
        "chat_template": render_official_template(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if mismatches or pip_check.returncode != 0:
        return 2
    if arguments.require_cuda and not cuda_available:
        return 2
    if arguments.expected_gpus and len(gpu_names) != arguments.expected_gpus:
        return 2
    if arguments.require_cuda and any("A100" not in name for name in gpu_names):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

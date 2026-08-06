#!/usr/bin/env python3
"""Verify the vLLM 0.6.1.post2 lm-format-enforcer import boundary."""

import importlib
from importlib.metadata import version
import sys

import lmformatenforcer
import transformers


EXPECTED_VLLM = "0.6.1.post2"
EXPECTED_LM_FORMAT_ENFORCER = "0.10.6"
EXPECTED_TRANSFORMERS = "4.45.2"
GUIDED_DECODING_BACKEND = "lm-format-enforcer"
VLLM_LMFE_MODULE = "vllm.model_executor.guided_decoding.lm_format_enforcer_decoding"


def main() -> None:
    """Import the precise compatibility boundary exercised by guided decoding."""
    assert version("vllm") == EXPECTED_VLLM
    assert version("lm-format-enforcer") == EXPECTED_LM_FORMAT_ENFORCER
    assert transformers.__version__ == EXPECTED_TRANSFORMERS

    from transformers.generation.logits_process import LogitsWarper
    from lmformatenforcer.integrations.transformers import (
        build_transformers_prefix_allowed_tokens_fn,
    )

    assert LogitsWarper is not None
    assert build_transformers_prefix_allowed_tokens_fn is not None
    modules_before = set(sys.modules)
    guided_module = importlib.import_module(VLLM_LMFE_MODULE)
    modules_after = set(sys.modules)
    forbidden = sorted(
        name
        for name in modules_after
        if name == "outlines"
        or name.startswith("outlines.")
        or name == "pyairports"
        or name.startswith("pyairports.")
    )
    assert guided_module is not None
    assert not forbidden, forbidden
    print("transformers:", transformers.__version__)
    print("lm-format-enforcer:", version("lm-format-enforcer"))
    print("guided-decoding-backend:", GUIDED_DECODING_BACKEND)
    print("vllm-guided-module:", VLLM_LMFE_MODULE)
    print("new-module-count:", len(modules_after - modules_before))
    print("outlines-or-pyairports-imported:", bool(forbidden))
    print("guided-decoding imports: OK")


if __name__ == "__main__":
    main()

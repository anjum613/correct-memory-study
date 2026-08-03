#!/usr/bin/env python3
"""Verify the vLLM 0.6.1.post2 guided-decoding compatibility contract."""

from importlib.metadata import version

import lmformatenforcer
import transformers


EXPECTED_VLLM = "0.6.1.post2"
EXPECTED_LM_FORMAT_ENFORCER = "0.10.6"
EXPECTED_TRANSFORMERS = "4.45.2"


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
    print("transformers:", transformers.__version__)
    print("lm-format-enforcer:", version("lm-format-enforcer"))
    print("guided-decoding imports: OK")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CPU-only offline tokenizer, config, vLLM, and chat-template probe."""

from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import (  # noqa: E402
    ENVIRONMENT_PATH,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    MODEL_TYPE,
    NATIVE_CONTEXT_LENGTH,
    SELECTED_CONTEXT_LENGTH,
    sha256_bytes,
    write_canonical_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.output.exists() or arguments.output.is_symlink():
        raise FileExistsError(f"compatibility output exists: {arguments.output}")
    if Path(sys.prefix).resolve(strict=True) != ENVIRONMENT_PATH.resolve(strict=True):
        raise RuntimeError("compatibility probe used the wrong interpreter")

    import torch
    from transformers import AutoTokenizer, PretrainedConfig
    from vllm.model_executor.models import ModelRegistry
    from vllm.reasoning import ReasoningParserManager
    from vllm.transformers_utils.config import get_config

    raw_config, unused = PretrainedConfig.get_config_dict(
        MODEL_SNAPSHOT,
        local_files_only=True,
        trust_remote_code=False,
    )
    vllm_config = get_config(
        MODEL_SNAPSHOT,
        trust_remote_code=False,
        revision=None,
        config_format="hf",
    )
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_SNAPSHOT,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    messages = [
        {"role": "system", "content": "You are a precise coding assistant."},
        {"role": "user", "content": "Reply with SMOKE_OK."},
    ]
    default_render = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    thinking_render = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )
    nonthinking_render = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    arg_utils_path = ENVIRONMENT_PATH / "lib/python3.12/site-packages/vllm/engine/arg_utils.py"
    cli_args_path = (
        ENVIRONMENT_PATH
        / "lib/python3.12/site-packages/vllm/entrypoints/openai/cli_args.py"
    )
    cli_source = arg_utils_path.read_text(encoding="utf-8") + cli_args_path.read_text(
        encoding="utf-8"
    )
    required_flags = (
        "--dtype",
        "--enforce-eager",
        "--gpu-memory-utilization",
        "--language-model-only",
        "--max-model-len",
        "--max-num-seqs",
        "--reasoning-parser",
        "--served-model-name",
        "--tensor-parallel-size",
    )
    registered_reasoning = ReasoningParserManager.list_registered()
    checks = {
        "architecture_registered_natively": (
            MODEL_ARCHITECTURE in ModelRegistry.get_supported_archs()
        ),
        "chat_template_default_is_thinking": default_render == thinking_render,
        "chat_template_modes_distinct": thinking_render != nonthinking_render,
        "config_loaded_without_remote_code": (
            raw_config.get("auto_map") in (None, {}) and not unused
        ),
        "model_identity": (
            raw_config.get("model_type") == MODEL_TYPE
            and raw_config.get("architectures") == [MODEL_ARCHITECTURE]
        ),
        "native_context_supports_selection": (
            raw_config.get("text_config", raw_config).get("max_position_embeddings")
            == NATIVE_CONTEXT_LENGTH
            and SELECTED_CONTEXT_LENGTH <= NATIVE_CONTEXT_LENGTH
        ),
        "qwen3_reasoning_parser_registered": "qwen3" in registered_reasoning,
        "server_cli_options_present": all(flag in cli_source for flag in required_flags),
        "tokenizer_loaded_offline": tokenizer.is_fast,
        "vllm_config_recognized": (
            getattr(vllm_config, "model_type", None) == MODEL_TYPE
            and getattr(vllm_config, "architectures", None)
            == [MODEL_ARCHITECTURE]
        ),
    }
    result = {
        "checks": checks,
        "chat_template": {
            "default_render_sha256": sha256_bytes(default_render.encode("utf-8")),
            "nonthinking_render_sha256": sha256_bytes(
                nonthinking_render.encode("utf-8")
            ),
            "thinking_enabled_by_default": default_render == thinking_render,
            "thinking_render_sha256": sha256_bytes(thinking_render.encode("utf-8")),
        },
        "custom_remote_code_required": False,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "no_automatic_conversation_summarization": True,
        "no_automatic_skills": True,
        "no_hidden_automatic_memory": True,
        "no_persistent_cross_session_state": True,
        "pass": all(checks.values()),
        "registered_reasoning_parsers": registered_reasoning,
        "schema": "qwen36-cpu-compatibility-probe-v1",
        "selected_context_length": SELECTED_CONTEXT_LENGTH,
        "server_cli_flag_source": [str(arg_utils_path), str(cli_args_path)],
        "versions": {
            "python": sys.version.split()[0],
            "tokenizers": version("tokenizers"),
            "torch": torch.__version__,
            "torch_cuda_build": torch.version.cuda,
            "transformers": version("transformers"),
            "vllm": version("vllm"),
        },
    }
    write_canonical_json(arguments.output, result, exclusive=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run one deterministic Hugging Face coding-model inference smoke test."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from cmpilot.artifact_logger import redact_text, write_text

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
PROMPT = """You are testing a coding model. Write a concise Python function named
safe_divide(a, b) that raises ValueError when b is zero and otherwise
returns a / b. Return only the code."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def append_event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def write_result(path: Path, result: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")


def has_zero_check(text: str) -> bool:
    return bool(re.search(r"\bif\s+(?:b\s*==\s*0|not\s+b)\s*:", text))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--model-id", default=MODEL_ID)
    args = parser.parse_args()
    artifact_dir = args.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "model_inference_result.json"
    event_path = artifact_dir / "model_inference_events.jsonl"
    result = {
        "artifact_schema": "model-inference-smoke-v1",
        "started_at_utc": now(),
        "status": "running",
        "model_id": args.model_id,
        "requested_dtype": "bfloat16",
    }
    append_event(event_path, {"event": "started", "at_utc": result["started_at_utc"]})

    try:
        import torch
        import transformers
        from huggingface_hub import model_info
        from transformers import AutoModelForCausalLM, AutoTokenizer

        result.update(
            python_version=sys.version,
            torch_version=torch.__version__,
            transformers_version=transformers.__version__,
            cuda_runtime_version=torch.version.cuda,
            cudnn_version=torch.backends.cudnn.version(),
            cuda_available=torch.cuda.is_available(),
        )
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        if torch.cuda.device_count() < 1:
            raise RuntimeError("no GPU is visible to this job")

        device = torch.device("cuda:0")
        gpu = torch.cuda.get_device_properties(device)
        result.update(
            gpu_count_visible=torch.cuda.device_count(),
            gpu_name=torch.cuda.get_device_name(device),
            gpu_total_memory_bytes=gpu.total_memory,
            gpu_compute_capability=list(torch.cuda.get_device_capability(device)),
        )
        revision = model_info(args.model_id).sha
        if not revision:
            raise RuntimeError("Hugging Face did not return a model revision")
        result["model_revision"] = revision
        write_text(artifact_dir / "model_revision.txt", revision + "\n")

        start = time.perf_counter()
        tokenizer = AutoTokenizer.from_pretrained(args.model_id, revision=revision)
        result["tokenizer_load_duration_seconds"] = time.perf_counter() - start
        start = time.perf_counter()
        model = AutoModelForCausalLM.from_pretrained(
            args.model_id, revision=revision, torch_dtype=torch.bfloat16
        ).to(device)
        model.eval()
        torch.cuda.synchronize(device)
        result["model_load_duration_seconds"] = time.perf_counter() - start
        result["memory_allocated_after_model_load_bytes"] = torch.cuda.memory_allocated(device)
        result["memory_reserved_after_model_load_bytes"] = torch.cuda.memory_reserved(device)

        input_ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": PROMPT}],
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(device)
        input_count = int(input_ids.shape[-1])
        attention_mask = torch.ones_like(input_ids, device=device)
        kwargs = {
            "attention_mask": attention_mask,
            "do_sample": False,
            "use_cache": True,
            "pad_token_id": tokenizer.eos_token_id,
        }
        with torch.inference_mode():
            model.generate(input_ids, max_new_tokens=8, **kwargs)
        torch.cuda.synchronize(device)

        torch.cuda.reset_peak_memory_stats(device)
        start = time.perf_counter()
        with torch.inference_mode():
            output_ids = model.generate(input_ids, max_new_tokens=128, **kwargs)
        torch.cuda.synchronize(device)
        duration = time.perf_counter() - start
        generated_ids = output_ids[:, input_count:]
        generated_count = int(generated_ids.shape[-1])
        text = tokenizer.decode(generated_ids[0], skip_special_tokens=True).strip()
        result.update(
            input_token_count=input_count,
            generated_token_count=generated_count,
            generation_duration_seconds=duration,
            generated_tokens_per_second=generated_count / duration if duration else None,
            peak_allocated_gpu_memory_bytes=torch.cuda.max_memory_allocated(device),
            peak_reserved_gpu_memory_bytes=torch.cuda.max_memory_reserved(device),
            generated_text=text,
            generated_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            output_non_empty=bool(text),
            contains_safe_divide="safe_divide" in text,
            contains_zero_divisor_check=has_zero_check(text),
        )
        write_text(artifact_dir / "generated_response.txt", text + "\n")
        if not result["output_non_empty"]:
            raise RuntimeError("generation produced empty output")
        if not result["contains_safe_divide"]:
            raise RuntimeError("generation output does not contain safe_divide")
        if not result["contains_zero_divisor_check"]:
            raise RuntimeError("generation output lacks a zero-divisor check")

        result.update(status="passed", finished_at_utc=now())
        write_result(result_path, result)
        append_event(event_path, {"event": "passed", "at_utc": result["finished_at_utc"]})
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except Exception as error:
        message = redact_text(str(error))
        result.update(
            status="failed",
            error_type=type(error).__name__,
            error_message=message,
            nan_or_inf_runtime_failure=bool(
                re.search(r"\b(?:nan|inf)\b", message, flags=re.IGNORECASE)
            ),
            traceback=redact_text(traceback.format_exc()),
            finished_at_utc=now(),
        )
        write_result(result_path, result)
        append_event(
            event_path,
            {
                "event": "failed",
                "at_utc": result["finished_at_utc"],
                "error_type": type(error).__name__,
            },
        )
        print(json.dumps(result, sort_keys=True, default=str), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

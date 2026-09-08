#!/usr/bin/env python3
"""Minimal single-GPU CUDA/PyTorch smoke test with a JSON result artifact."""

from __future__ import annotations

import argparse
import math
import platform
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cmpilot.artifact_logger import write_json


class SmokeFailure(RuntimeError):
    """A required GPU smoke-test check did not pass."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--matrix-size", type=int, default=1024)
    return parser.parse_args()


def dtype_name(dtype: Any) -> str:
    return str(dtype).replace("torch.", "")


def bf16_supported(torch: Any, index: int) -> bool:
    torch.cuda.set_device(index)
    try:
        return bool(torch.cuda.is_bf16_supported(index))
    except TypeError:
        return bool(torch.cuda.is_bf16_supported())


def run_matmul(torch: Any, index: int, dtype: Any, matrix_size: int) -> dict[str, Any]:
    torch.cuda.set_device(index)
    torch.cuda.reset_peak_memory_stats(index)
    left = right = result = None
    try:
        left = torch.randn((matrix_size, matrix_size), dtype=dtype, device=index)
        right = torch.randn((matrix_size, matrix_size), dtype=dtype, device=index)
        torch.cuda.synchronize(index)
        started = torch.cuda.Event(enable_timing=True)
        finished = torch.cuda.Event(enable_timing=True)
        started.record()
        result = torch.matmul(left, right)
        finished.record()
        torch.cuda.synchronize(index)
        elapsed_ms = float(started.elapsed_time(finished))
        is_finite = bool(torch.isfinite(result).all().item())
        checksum = float(result.float().sum().item())
        if not is_finite or not math.isfinite(checksum):
            raise SmokeFailure(f"{dtype_name(dtype)} produced NaN or infinity on GPU {index}")
        return {
            "status": "passed",
            "elapsed_ms": elapsed_ms,
            "checksum": checksum,
            "allocated_bytes": int(torch.cuda.memory_allocated(index)),
            "reserved_bytes": int(torch.cuda.memory_reserved(index)),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(index)),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(index)),
        }
    except Exception as error:
        return {"status": "failed", "error": f"{type(error).__name__}: {error}"}
    finally:
        del left, right, result
        torch.cuda.empty_cache()
        torch.cuda.synchronize(index)


def main() -> int:
    args = parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.artifact_dir / "gpu_smoke_result.json"
    payload: dict[str, Any] = {
        "status": "failed",
        "started_at": utc_now(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "matrix_size": args.matrix_size,
        "devices": [],
    }
    try:
        import torch

        payload.update(
            {
                "torch_version": torch.__version__,
                "cuda_runtime_version": torch.version.cuda,
                "cudnn_version": torch.backends.cudnn.version(),
                "cuda_available": bool(torch.cuda.is_available()),
                "gpu_count": int(torch.cuda.device_count()),
            }
        )
        print(f"Python: {platform.python_version()}")
        print(f"PyTorch: {torch.__version__}")
        print(f"CUDA runtime: {torch.version.cuda}")
        print(f"cuDNN: {torch.backends.cudnn.version()}")
        print(f"CUDA available: {torch.cuda.is_available()}")
        print(f"GPU count: {torch.cuda.device_count()}")
        if not torch.cuda.is_available():
            raise SmokeFailure("CUDA is unavailable")
        if torch.cuda.device_count() < 1:
            raise SmokeFailure("no GPU is visible")

        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            device: dict[str, Any] = {
                "index": index,
                "name": properties.name,
                "total_memory_bytes": int(properties.total_memory),
                "compute_capability": f"{properties.major}.{properties.minor}",
                "tests": {},
            }
            print(
                f"GPU {index}: {properties.name}; memory={properties.total_memory}; "
                f"compute_capability={properties.major}.{properties.minor}"
            )
            dtypes = [torch.float32, torch.float16]
            if bf16_supported(torch, index):
                dtypes.append(torch.bfloat16)
            else:
                device["tests"]["bfloat16"] = {"status": "skipped", "reason": "not supported"}
            for dtype in dtypes:
                name = dtype_name(dtype)
                test = run_matmul(torch, index, dtype, args.matrix_size)
                device["tests"][name] = test
                print(f"GPU {index} {name}: {test}")
                if test["status"] != "passed":
                    raise SmokeFailure(f"{name} operation failed on GPU {index}: {test['error']}")
            if device["tests"]["float32"]["status"] != "passed":
                raise SmokeFailure(f"FP32 operation failed on GPU {index}")
            payload["devices"].append(device)
        payload["status"] = "passed"
    except Exception as error:
        payload["error"] = f"{type(error).__name__}: {error}"
        payload["traceback"] = traceback.format_exc()
        print(payload["error"], file=sys.stderr)
    finally:
        payload["finished_at"] = utc_now()
        write_json(result_path, payload)
        print(f"Result JSON: {result_path}")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

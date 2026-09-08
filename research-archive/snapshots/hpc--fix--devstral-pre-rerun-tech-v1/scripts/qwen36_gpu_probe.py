#!/usr/bin/env python3
"""Record two-rank NCCL and CUDA capability evidence for the Qwen3.6 smoke."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

import torch
import torch.distributed as distributed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", required=True, type=Path)
    arguments = parser.parse_args()
    artifact = arguments.artifact_directory.resolve(strict=True)
    rank = int(os.environ["RANK"])
    local_rank = int(os.environ["LOCAL_RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    if world_size != 2:
        raise RuntimeError(f"expected exactly two NCCL ranks, found {world_size}")
    distributed.init_process_group("nccl")
    torch.cuda.set_device(local_rank)
    value = torch.tensor([float(rank + 1)], device=f"cuda:{local_rank}")
    distributed.all_reduce(value)
    properties = torch.cuda.get_device_properties(local_rank)
    record = {
        "all_reduce_expected": 3.0,
        "all_reduce_observed": value.item(),
        "bf16_supported": torch.cuda.is_bf16_supported(),
        "cuda_device_count": torch.cuda.device_count(),
        "cuda_version": torch.version.cuda,
        "device_name": properties.name,
        "local_rank": local_rank,
        "nccl_available": distributed.is_nccl_available(),
        "pass": (
            value.item() == 3.0
            and torch.cuda.device_count() == 2
            and properties.name == "NVIDIA A100-PCIE-40GB"
            and torch.cuda.is_bf16_supported()
        ),
        "peer_access_matrix": [
            [torch.cuda.can_device_access_peer(left, right) if left != right else True
             for right in range(torch.cuda.device_count())]
            for left in range(torch.cuda.device_count())
        ],
        "rank": rank,
        "schema": "qwen36-two-rank-nccl-probe-v1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "total_memory_bytes": properties.total_memory,
        "torch_version": torch.__version__,
        "world_size": world_size,
    }
    path = artifact / f"nccl-rank-{rank}.json"
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    distributed.barrier()
    distributed.destroy_process_group()
    print(json.dumps(record, sort_keys=True))
    return 0 if record["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

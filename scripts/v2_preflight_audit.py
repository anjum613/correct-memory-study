#!/usr/bin/env python3
"""Generate reproducible V2 immutability and exact prompt-census artifacts."""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from typing import Any, Iterable

from cmpilot.v2_preflight import V2ContextProfile
from cmpilot.v2_prompting import NO_MEMORY, SOURCE_CORRECT_MEMORY, build_initial_prompt


ROOT = Path(__file__).parents[1]
EXTERNAL_V1 = Path("/home/s224049759/final-experiment-artifacts/post-primary-strengthening-v1")
FAMILY_REFS = {
    "mcp-pinot-v1": "61834933c4301ab706fe967ec455f3014d55028b",
    "onnx-v1": "7c8ff4d4e5cedaea61333205fa4fbb6b32ddce2b",
    "axios-v1": "a09acc9996f5f5461b1f5314026a961456ac4ebb",
    "aim-v1": "1c66c6306834fff5adf4be6157a9f14af35b2da1",
    "httpx-v1": "802a30ae2a2f7a453407922ca69e331ce3f74f0e",
    "djoser-v1": "61834933c4301ab706fe967ec455f3014d55028b",
}
MODEL_REFS = {
    "final-runtime": "c1794fdecffc58b82256ef74558e96dff31b0176",
    "latest-six-family-infrastructure": "61834933c4301ab706fe967ec455f3014d55028b",
}
MISTRAL_COMMON_SITE = Path(
    "/home/s224049759/environments/devstral-small-2507-agent-v1/"
    "lib/python3.11/site-packages"
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def git_paths(ref: str, prefixes: Iterable[str]) -> list[str]:
    paths = git("ls-tree", "-r", "--name-only", ref).decode().splitlines()
    return sorted(path for path in paths if any(path.startswith(prefix) for prefix in prefixes))


def write_json(path: Path, value: Any) -> str:
    payload = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return sha256(payload)


def build_v1_manifest(output: Path) -> dict[str, Any]:
    family_records: list[dict[str, Any]] = []
    metadata_prefixes = (
        "family-package.json",
        "memories/",
        "oracles/",
        "provenance/",
        "references/",
        "task-policy.json",
        "tasks/",
        "validation/",
    )
    for family, ref in FAMILY_REFS.items():
        root = f"families/{family}/"
        all_paths = git_paths(ref, (root,))
        selected = [
            path
            for path in all_paths
            if any(path[len(root) :].startswith(prefix) for prefix in metadata_prefixes)
        ]
        files = []
        for path in selected:
            payload = git("show", f"{ref}:{path}")
            files.append({"path": path, "sha256": sha256(payload), "bytes": len(payload)})
        repository_trees = []
        for state in ("source", "compatible", "invalidated"):
            tree_path = f"families/{family}/repositories/{state}"
            try:
                tree = git("rev-parse", f"{ref}:{tree_path}").decode().strip()
            except subprocess.CalledProcessError:
                tree = None
            repository_trees.append({"state": state, "path": tree_path, "git_tree": tree})
        family_records.append(
            {
                "family": family,
                "ref": ref,
                "files": files,
                "repository_trees": repository_trees,
            }
        )

    shared_files = []
    shared_prefixes = (
        "configs/agent/",
        "configs/experiments/conditions/",
        "configs/models/",
        "docs/methodology/",
        "methodology/",
        "src/cmpilot/final_",
        "src/cmpilot/experiment_models.py",
        "src/cmpilot/devstral_",
        "src/cmpilot/integrations/miniswe/",
        "slurm/final_experiment_array.sbatch",
    )
    for label, ref in MODEL_REFS.items():
        for path in git_paths(ref, shared_prefixes):
            payload = git("show", f"{ref}:{path}")
            shared_files.append(
                {"source": label, "ref": ref, "path": path, "sha256": sha256(payload), "bytes": len(payload)}
            )

    external = []
    for path in sorted(item for item in EXTERNAL_V1.rglob("*") if item.is_file()):
        payload = path.read_bytes()
        external.append(
            {
                "path": str(path),
                "relative_path": path.relative_to(EXTERNAL_V1).as_posix(),
                "sha256": sha256(payload),
                "bytes": len(payload),
            }
        )
    record = {
        "schema": "cmpilot-v1-immutability-manifest-v1",
        "family_sources": family_records,
        "shared_v1_files": shared_files,
        "external_archive": {"root": str(EXTERNAL_V1), "files": external},
        "exclusions": ["large model weights are represented by existing frozen metadata, not re-hashed here"],
    }
    digest = write_json(output, record)
    return {"path": str(output), "sha256": digest, "family_count": len(family_records), "external_file_count": len(external)}


def _counter(model: str):
    if model == "qwen":
        from cmpilot.integrations.miniswe.context_budget import ExactQwenChatTokenCounter

        return ExactQwenChatTokenCounter(
            Path("/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/381fc969f78efac66bc87ff7ddeadb7e73c218a7")
        )
    if model == "devstral":
        # The frozen Devstral environment is on intermittently unhealthy
        # network storage.  For the offline text-only audit, load its exact
        # pure-Python mistral-common 1.8.4 package into the already-qualified
        # tokenizer interpreter.  mistral-common imports PIL for optional
        # image messages even though this protocol admits text only; a tiny
        # nonfunctional type shim avoids importing an incompatible CPython
        # extension from the frozen Python 3.11 environment.
        try:
            import PIL  # noqa: F401
        except ImportError:
            pil = types.ModuleType("PIL")
            image = types.ModuleType("PIL.Image")

            class TextOnlyImage:
                pass

            image.Image = TextOnlyImage
            image.open = _reject_image_input
            pil.Image = image
            sys.modules["PIL"] = pil
            sys.modules["PIL.Image"] = image
        if not MISTRAL_COMMON_SITE.is_dir():
            raise RuntimeError(
                f"pinned mistral-common site is unavailable: {MISTRAL_COMMON_SITE}"
            )
        sys.path.append(str(MISTRAL_COMMON_SITE))
        from cmpilot.devstral_serialization import ExactMistralChatTokenCounter

        return ExactMistralChatTokenCounter(
            Path("/home/s224049759/model-cache/huggingface/hub/models--mistralai--Devstral-Small-2507/snapshots/bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39")
        )
    raise ValueError(model)


def _reject_image_input(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("image input is outside the text-only V2 prompt census")


def _raw_count(counter: Any, text: str, model: str) -> int | None:
    if model == "qwen":
        return len(counter._tokenizer.encode(text, add_special_tokens=False).ids)
    tokenizer = getattr(getattr(counter._tokenizer, "instruct_tokenizer", None), "tokenizer", None)
    encode = getattr(tokenizer, "encode", None)
    if encode is None:
        return None
    for kwargs in ({"bos": False, "eos": False}, {}):
        try:
            value = encode(text, **kwargs)
            return len(value)
        except TypeError:
            continue
    return None


def build_prompt_census(model: str, output_root: Path) -> dict[str, Any]:
    counter = _counter(model)
    profile = V2ContextProfile()
    cells = []
    output_root = Path(output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    prompt_root = output_root / "rendered-prompts" / model
    for family in FAMILY_REFS:
        for condition in (NO_MEMORY, SOURCE_CORRECT_MEMORY):
            prompt = build_initial_prompt(ROOT / "families" / family, condition)
            messages = list(prompt.messages)
            rendered = counter.render(messages)
            p = counter.count(messages)
            payload = rendered.encode("utf-8")
            prompt_path = prompt_root / f"{family}--{condition}.txt"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_bytes(payload)
            total = p + profile.trajectory_budget + profile.safety_reserve
            cells.append(
                {
                    "family": family,
                    "model": model,
                    "condition": condition,
                    "prompt_tokens_P": p,
                    "memory_tokens": 0 if prompt.memory_text is None else _raw_count(counter, prompt.memory_text, model),
                    "tool_schema_tokens": 0,
                    "tool_schema_note": "OpenAI request tools=None; text-action contract is included in system_tokens",
                    "system_tokens": _raw_count(counter, messages[0]["content"], model),
                    "task_tokens": _raw_count(counter, prompt.task_text, model),
                    "p_plus_trajectory_budget_plus_reserve": total,
                    "fits_32768": total <= profile.physical_context,
                    "remaining_physical_margin": profile.physical_context - total,
                    "rendered_prompt_path": prompt_path.relative_to(ROOT).as_posix(),
                    "rendered_prompt_sha256": sha256(payload),
                    "rendered_prompt_bytes": len(payload),
                }
            )
    record = {
        "schema": "cmpilot-v2-prompt-census-v1",
        "model": model,
        "tokenizer": counter.identity,
        "profile": asdict_profile(profile),
        "cells": cells,
    }
    write_json(output_root / f"token-census-{model}.json", record)
    return record


_DTYPE_BYTES = {"BF16": 2, "F16": 2, "F32": 4, "I64": 8, "I32": 4}


def _safetensors_stats(paths: Iterable[Path]) -> dict[str, Any]:
    parameters = 0
    tensor_bytes = 0
    tensors = 0
    dtypes: set[str] = set()
    files = list(paths)
    for path in files:
        with path.open("rb") as stream:
            header_size = int.from_bytes(stream.read(8), "little")
            header = json.loads(stream.read(header_size))
        for name, row in header.items():
            if name == "__metadata__":
                continue
            count = functools.reduce(lambda left, right: left * right, row["shape"], 1)
            dtype = row["dtype"]
            parameters += count
            tensor_bytes += count * _DTYPE_BYTES[dtype]
            tensors += 1
            dtypes.add(dtype)
    return {
        "files": len(files),
        "parameters": parameters,
        "tensor_bytes": tensor_bytes,
        "tensor_gib": tensor_bytes / 2**30,
        "tensors": tensors,
        "dtypes": sorted(dtypes),
    }


def _model_hardware_row(
    *, name: str, snapshot: Path, weight_paths: Iterable[Path]
) -> dict[str, Any]:
    config = json.loads((snapshot / "config.json").read_text())
    stats = _safetensors_stats(weight_paths)
    layers = int(config["num_hidden_layers"])
    kv_heads = int(config["num_key_value_heads"])
    head_dim = int(
        config.get("head_dim", config["hidden_size"] // config["num_attention_heads"])
    )
    context = 32768
    kv_bytes = 2 * layers * kv_heads * head_dim * 2 * context
    overhead_gib = max(4.0, stats["tensor_gib"] * 0.10)
    estimated_total = stats["tensor_gib"] + kv_bytes / 2**30 + overhead_gib
    return {
        "model": name,
        "revision": snapshot.name,
        "architecture": config["architectures"][0],
        "weight_dtype": config.get("torch_dtype"),
        "weights": stats,
        "layers": layers,
        "hidden_size": int(config["hidden_size"]),
        "attention_heads": int(config["num_attention_heads"]),
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "kv_cache": {
            "context": context,
            "concurrency": 1,
            "dtype": "bfloat16",
            "bytes": kv_bytes,
            "gib": kv_bytes / 2**30,
        },
        "estimated_runtime_overhead_gib": overhead_gib,
        "estimated_total_vram_gib": estimated_total,
        "estimate_formula": (
            "BF16 weights + BF16 K/V cache + max(4 GiB, 10% weight runtime overhead)"
        ),
        "tp1_conservative_fit": {
            "A100_80_GB": estimated_total <= 72.0,
            "H100_80_GB": estimated_total <= 72.0,
            "H100_NVL_94_GB": estimated_total <= 84.6,
            "H200_141_GB": estimated_total <= 126.9,
        },
    }


def build_hardware_estimates(output: Path) -> dict[str, Any]:
    qwen = Path(
        "/home/s224049759/model-cache/huggingface/hub/"
        "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
        "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
    )
    devstral = Path(
        "/home/s224049759/model-cache/huggingface/hub/"
        "models--mistralai--Devstral-Small-2507/snapshots/"
        "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
    )
    record = {
        "schema": "cmpilot-v2-hardware-estimates-v1",
        "measurement_kind": "local exact weight headers plus engineering estimate",
        "gpu_runtime_measurement_status": "NOT_TESTED_NO_GPU",
        "models": [
            _model_hardware_row(
                name="Qwen/Qwen2.5-Coder-32B-Instruct",
                snapshot=qwen,
                weight_paths=sorted(qwen.glob("model-*.safetensors")),
            ),
            _model_hardware_row(
                name="mistralai/Devstral-Small-2507",
                snapshot=devstral,
                weight_paths=(devstral / "consolidated.safetensors",),
            ),
        ],
        "notes": [
            "fit threshold assumes vLLM gpu_memory_utilization=0.90",
            "allocator fragmentation and CUDA graph/workspace use require GPU qualification",
        ],
    }
    write_json(output, record)
    return record


def asdict_profile(profile: V2ContextProfile) -> dict[str, int]:
    return {
        "physical_context": profile.physical_context,
        "trajectory_budget": profile.trajectory_budget,
        "safety_reserve": profile.safety_reserve,
        "per_turn_generation_ceiling": profile.per_turn_generation_ceiling,
        "maximum_model_decisions": profile.maximum_model_decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    manifest = sub.add_parser("v1-manifest")
    manifest.add_argument("--output", type=Path, default=ROOT / "artifacts/v2-preflight/v1-immutability.json")
    census = sub.add_parser("prompt-census")
    census.add_argument("--model", choices=("qwen", "devstral"), required=True)
    census.add_argument("--output-root", type=Path, default=ROOT / "artifacts/v2-preflight")
    hardware = sub.add_parser("hardware")
    hardware.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/v2-preflight/hardware-estimates.json",
    )
    args = parser.parse_args()
    if args.command == "v1-manifest":
        print(json.dumps(build_v1_manifest(args.output), sort_keys=True))
    elif args.command == "prompt-census":
        value = build_prompt_census(args.model, args.output_root)
        print(json.dumps({"model": args.model, "cells": len(value["cells"])}, sort_keys=True))
    else:
        value = build_hardware_estimates(args.output)
        print(
            json.dumps(
                {"models": len(value["models"]), "output": str(args.output)},
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

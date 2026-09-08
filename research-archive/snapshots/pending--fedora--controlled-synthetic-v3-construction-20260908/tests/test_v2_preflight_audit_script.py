from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _module():
    spec = importlib.util.spec_from_file_location("v2_preflight_audit", ROOT / "scripts/v2_preflight_audit.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_family_ref_inventory_is_exactly_six() -> None:
    module = _module()
    assert tuple(module.FAMILY_REFS) == (
        "mcp-pinot-v1",
        "onnx-v1",
        "axios-v1",
        "aim-v1",
        "httpx-v1",
        "djoser-v1",
    )


def test_canonical_json_is_stable() -> None:
    module = _module()
    assert module.canonical({"b": 1, "a": 2}) == b'{\n  "a": 2,\n  "b": 1\n}\n'


def test_local_exact_weight_headers_and_kv_estimates(tmp_path: Path) -> None:
    module = _module()
    record = module.build_hardware_estimates(tmp_path / "hardware.json")
    qwen, devstral = record["models"]
    assert qwen["weights"]["parameters"] == 32_763_876_352
    assert qwen["kv_cache"]["bytes"] == 8 * 2**30
    assert devstral["weights"]["parameters"] == 23_572_403_200
    assert devstral["kv_cache"]["bytes"] == 5 * 2**30

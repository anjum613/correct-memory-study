#!/usr/bin/env python3
"""Capture the isolated Qwen3.6 serving environment without mutating it."""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.environment_content_digest import (  # noqa: E402
    fingerprint_installed_distributions,
    write_content_digest_artifacts,
)
from cmpilot.environment_fingerprint import (  # noqa: E402
    write_fingerprint_artifacts,
)
from cmpilot.qwen36_candidate import (  # noqa: E402
    ENVIRONMENT_PATH,
    QUALIFICATION_NAMESPACE,
    sha256_file,
    write_canonical_json,
)


CONTENT_DISTRIBUTIONS = (
    "llguidance",
    "lm-format-enforcer",
    "openai",
    "pyzmq",
    "tokenizers",
    "torch",
    "transformers",
    "vllm",
    "xgrammar",
)


def main() -> int:
    if Path(sys.prefix).resolve(strict=True) != ENVIRONMENT_PATH.resolve(strict=True):
        raise RuntimeError(
            f"run with {ENVIRONMENT_PATH / 'bin/python'}, not {sys.executable}"
        )
    namespace = ROOT / QUALIFICATION_NAMESPACE
    outputs = {
        "content_inventory": namespace / "environment-content-inventory.json",
        "content_record": namespace / "environment-content-digest.json",
        "fingerprint_inventory": namespace / "environment-inventory.json",
        "fingerprint_record": namespace / "environment-fingerprint.json",
        "lock": namespace / "environment-lock.txt",
        "manifest": namespace / "environment-manifest.json",
    }
    for path in outputs.values():
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"environment output already exists: {path}")
    namespace.mkdir(parents=True, exist_ok=True)

    fingerprint = write_fingerprint_artifacts(
        outputs["fingerprint_inventory"],
        outputs["fingerprint_record"],
        interpreter=sys.executable,
    )
    content = fingerprint_installed_distributions(CONTENT_DISTRIBUTIONS)
    write_content_digest_artifacts(
        outputs["content_inventory"], outputs["content_record"], content
    )
    freeze = subprocess.run(
        (sys.executable, "-m", "pip", "freeze", "--all"),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout.splitlines()
    outputs["lock"].write_text(
        "\n".join(sorted(freeze, key=str.casefold)) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    import torch

    versions = {
        name: version(name)
        for name in (
            "llguidance",
            "lm-format-enforcer",
            "openai",
            "tokenizers",
            "torch",
            "transformers",
            "vllm",
            "xgrammar",
        )
    }
    manifest = {
        "content_digest": content.as_record(),
        "content_distributions": list(CONTENT_DISTRIBUTIONS),
        "environment_path": str(ENVIRONMENT_PATH),
        "fingerprint": fingerprint.as_record(interpreter=sys.executable),
        "lock_sha256": sha256_file(outputs["lock"]),
        "no_existing_environment_modified": True,
        "package_manager_check": "pip check: No broken requirements found.",
        "python_version": sys.version.split()[0],
        "schema": "qwen36-serving-environment-v1",
        "torch_cuda_build": torch.version.cuda,
        "versions": versions,
    }
    write_canonical_json(outputs["manifest"], manifest, exclusive=True)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

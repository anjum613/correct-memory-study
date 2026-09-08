#!/usr/bin/env python3
"""Reproduce the HTTPX advisory fix boundary without selecting Track B S/C/I."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.final_experiment import canonical_json_bytes  # noqa: E402


SCHEMA = "cmpilot-httpx-non-final-fix-boundary-probe-v1"
VULNERABLE_REVISION = "b07fe7b0745e62be5ef9bce1bee9e7d7a8878552"
VULNERABLE_TREE = "148c36cfca267bded8ad2700ce25ae25d211c508"
FIX_REVISION = "e9b0c85dd4f4e4469c57c4b38e5101fd12081b5c"
FIX_TREE = "0ecd98de96929a6597b34e5ee490a6a04d87b356"
EXPECTED_CHANGED_FILES = ("httpx/_urls.py", "tests/models/test_url.py")

_PROBE_SOURCE = r"""
import json
import httpx

url = httpx.URL("https://u:p@[invalid!]//evilHost/path?t=w#tw")
before = {
    "netloc": url.netloc.decode("ascii"),
    "raw_path": url.raw_path.decode("ascii"),
}
copied = url.copy_with(userinfo=b"")
after = {
    "netloc": copied.netloc.decode("ascii"),
    "raw_path": copied.raw_path.decode("ascii"),
}
print(json.dumps({"after": after, "before": before}, sort_keys=True))
"""


class ProbeError(RuntimeError):
    """The supplied upstream repository or runtime is not qualified."""


def _git(repository: Path, *arguments: str, binary: bool = False) -> str | bytes:
    process = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        check=False,
        timeout=30,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise ProbeError(f"git {' '.join(arguments)} failed: {detail}")
    return process.stdout if binary else process.stdout.decode("utf-8").strip()


def _revision_metadata(repository: Path, revision: str) -> dict[str, Any]:
    commit = _git(repository, "rev-parse", f"{revision}^{{commit}}")
    tree = _git(repository, "rev-parse", f"{revision}^{{tree}}")
    parents = _git(repository, "show", "-s", "--format=%P", revision)
    subject = _git(repository, "show", "-s", "--format=%s", revision)
    return {
        "commit": commit,
        "parents": str(parents).split(),
        "subject": subject,
        "tree": tree,
    }


def _extract_revision(repository: Path, revision: str, destination: Path) -> None:
    archive = _git(repository, "archive", "--format=tar", revision, binary=True)
    assert isinstance(archive, bytes)
    destination.mkdir(mode=0o700)
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as stream:
        stream.extractall(destination, filter="data")


def _run_revision_probe(
    *, python: Path, repository: Path, revision: str, scratch: Path
) -> Mapping[str, Any]:
    snapshot = scratch / revision
    _extract_revision(repository, revision, snapshot)
    environment = {
        "HOME": str(scratch),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": str(python.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONPATH": str(snapshot),
        "TMPDIR": str(scratch),
    }
    process = subprocess.run(
        [str(python), "-c", _PROBE_SOURCE],
        cwd=scratch,
        env=environment,
        capture_output=True,
        check=False,
        timeout=20,
        text=True,
    )
    if process.returncode != 0:
        raise ProbeError(
            f"probe failed for {revision}: {process.stderr.strip()}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise ProbeError(f"probe returned invalid JSON for {revision}") from error
    if not isinstance(payload, Mapping):
        raise ProbeError(f"probe returned a non-object for {revision}")
    return payload


def classify_observations(
    vulnerable: Mapping[str, Any], fixed: Mapping[str, Any]
) -> dict[str, bool]:
    """Classify only the frozen advisory regression-test observation."""

    original = {"netloc": "", "raw_path": "//evilHost/path?t=w"}
    changed = {"netloc": "evilhost", "raw_path": "/path?t=w"}
    return {
        "fix_preserves_original_components": (
            fixed.get("before") == original and fixed.get("after") == original
        ),
        "parent_reinterprets_path_as_authority": (
            vulnerable.get("before") == original
            and vulnerable.get("after") == changed
        ),
    }


def probe(repository: Path, python: Path) -> dict[str, Any]:
    supplied_repository = repository
    supplied_python = python
    if supplied_repository.is_symlink() or not supplied_repository.is_dir():
        raise ProbeError("upstream repository must be a real directory")
    if not supplied_python.is_file():
        raise ProbeError("qualified Python must resolve to a real file")
    repository = supplied_repository.resolve(strict=True)
    python = supplied_python.absolute()
    if not os.access(python, os.X_OK):
        raise ProbeError("qualified Python is not executable")

    vulnerable_metadata = _revision_metadata(repository, VULNERABLE_REVISION)
    fixed_metadata = _revision_metadata(repository, FIX_REVISION)
    if vulnerable_metadata["commit"] != VULNERABLE_REVISION:
        raise ProbeError("vulnerable revision does not resolve exactly")
    if vulnerable_metadata["tree"] != VULNERABLE_TREE:
        raise ProbeError("vulnerable tree mismatch")
    if fixed_metadata["commit"] != FIX_REVISION:
        raise ProbeError("fix revision does not resolve exactly")
    if fixed_metadata["tree"] != FIX_TREE:
        raise ProbeError("fix tree mismatch")
    if fixed_metadata["parents"] != [VULNERABLE_REVISION]:
        raise ProbeError("fix parent mismatch")
    changed_files = tuple(
        str(
            _git(
                repository,
                "diff",
                "--name-only",
                VULNERABLE_REVISION,
                FIX_REVISION,
            )
        ).splitlines()
    )
    if changed_files != EXPECTED_CHANGED_FILES:
        raise ProbeError("fix changed-file set mismatch")

    with tempfile.TemporaryDirectory(prefix="cmpilot-httpx-boundary-") as temporary:
        scratch = Path(temporary)
        vulnerable_observation = _run_revision_probe(
            python=python,
            repository=repository,
            revision=VULNERABLE_REVISION,
            scratch=scratch,
        )
        fixed_observation = _run_revision_probe(
            python=python,
            repository=repository,
            revision=FIX_REVISION,
            scratch=scratch,
        )
    checks = classify_observations(vulnerable_observation, fixed_observation)
    passed = all(checks.values())
    return {
        "checks": checks,
        "classification": "NON_FINAL_ADVISORY_FIX_BOUNDARY_ONLY",
        "complete": True,
        "fixed": {
            "metadata": fixed_metadata,
            "observation": fixed_observation,
        },
        "passed": passed,
        "schema": SCHEMA,
        "scientific_claims": {
            "final_p_star_established": False,
            "final_s_c_i_selected": False,
            "family_freeze_permitted": False,
            "source_memory_generation_permitted": False,
        },
        "vulnerable_parent": {
            "metadata": vulnerable_metadata,
            "observation": vulnerable_observation,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repository", required=True, type=Path)
    parser.add_argument("--qualified-python", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        result = probe(arguments.upstream_repository, arguments.qualified_python)
    except (OSError, ProbeError, subprocess.SubprocessError, tarfile.TarError) as error:
        result = {
            "classification": "NON_FINAL_ADVISORY_FIX_BOUNDARY_ONLY",
            "complete": False,
            "error": f"{type(error).__name__}: {error}",
            "passed": None,
            "schema": SCHEMA,
        }
        sys.stdout.buffer.write(canonical_json_bytes(result))
        return 2
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

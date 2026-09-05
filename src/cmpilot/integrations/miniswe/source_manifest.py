"""Pinned mini-SWE-agent 2.4.6 source-integrity manifest."""

from __future__ import annotations

import hashlib
import importlib.util
from importlib.metadata import version
from pathlib import Path
from typing import Any


EXPECTED_VERSION = "2.4.6"
EXPECTED_SOURCE_HASHES = {
    "__init__.py": "0a708308b1b62cc020b60799c3d54f665845f795b3f0c4fdac787c96a38d12c7",
    "agents/default.py": "e8ef8aa365942d739c2ec5cb0879f60f377d2dc2de8ec670aaedf3bafb45a4c2",
    "config/default.yaml": "112aa58328f478a41cc2630702a4b89ef459e912870e05065157ed221f56701f",
    "environments/local.py": "01dd33ae6be897458611911cc0eee1389092ea9fc6788c7eb24773e7c6342b1c",
    "exceptions.py": "0590393c56bee873c79a691dcb4f15cb39c85f1658598b84bfb295bfde56921d",
    "models/__init__.py": "eb141eae346d51af407b4faf868ad7e869fa4fff275415381fa8ef845616f351",
    "models/litellm_model.py": "6df4483bcdc9620b2f9d7f8bb1027a7fb9729b739976cbcf1a9d18fb58c48227",
    "models/litellm_textbased_model.py": "395bc9bc4a06c18577e73b21c5465f9d22a6d0cc45b006f3d7c9fdaae399e732",
    "models/utils/actions_toolcall.py": "47b666412e4f838508b50009cf34c7f63fe15e9e40affc257a17c0829896526f",
    "models/utils/actions_text.py": "e5997bba3ae3d541ff418317cc8dd9e9e17657de806679ef38ab1ad74e294047",
}


class MiniSWESourceIntegrityError(RuntimeError):
    """Installed mini-SWE sources differ from the inspected 2.4.6 files."""


def collect_installed_source_manifest() -> dict[str, Any]:
    spec = importlib.util.find_spec("minisweagent")
    if spec is None or spec.origin is None:
        raise MiniSWESourceIntegrityError("mini-SWE-agent package cannot be located")
    package_root = Path(spec.origin).resolve().parent
    sources: dict[str, dict[str, Any]] = {}
    for relative_path, expected_hash in sorted(EXPECTED_SOURCE_HASHES.items()):
        path = package_root / relative_path
        if not path.is_file():
            sources[relative_path] = {
                "actual_sha256": None,
                "expected_sha256": expected_hash,
                "matches": False,
                "path": str(path),
            }
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        sources[relative_path] = {
            "actual_sha256": actual_hash,
            "expected_sha256": expected_hash,
            "matches": actual_hash == expected_hash,
            "path": str(path.resolve()),
        }
    installed_version = version("mini-swe-agent")
    return {
        "all_match": installed_version == EXPECTED_VERSION
        and all(record["matches"] for record in sources.values()),
        "expected_version": EXPECTED_VERSION,
        "installed_version": installed_version,
        "package_root": str(package_root),
        "sources": sources,
    }


def require_installed_sources_unchanged() -> dict[str, Any]:
    manifest = collect_installed_source_manifest()
    if not manifest["all_match"]:
        mismatches = [
            path
            for path, record in manifest["sources"].items()
            if not record["matches"]
        ]
        raise MiniSWESourceIntegrityError(
            "installed mini-SWE-agent source mismatch: "
            f"version={manifest['installed_version']!r}, paths={mismatches}"
        )
    return manifest

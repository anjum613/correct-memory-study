from __future__ import annotations

import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys

import pytest

from cmpilot.environment_fingerprint import (
    SCHEMA_VERSION,
    FingerprintSchemaMismatch,
    canonical_inventory_bytes,
    compare_fingerprint_records,
    fingerprint_records,
    load_inventory_records,
    write_fingerprint_artifacts,
)


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
LOGIN_FIXTURE = FIXTURES / "job_25033_packages_login.json"
BATCH_FIXTURE = FIXTURES / "job_25033_packages_batch.json"
RUNTIME = {"python_implementation": "CPython", "python_version": "3.12.8"}
SAMPLE_RECORDS = [
    {"name": "Zulu", "version": "2.0"},
    {"name": "alpha_pkg", "version": "1.0"},
    {"name": "Bravo.Pkg", "version": "3.0"},
]


def _clean_locale_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key == "LANG" or key.startswith("LC_"):
            environment.pop(key)
    environment["PYTHONPATH"] = str(ROOT / "src")
    return environment


def _locale_is_available(name: str) -> bool:
    environment = _clean_locale_environment()
    environment.update({"LANG": name, "LC_ALL": name})
    result = subprocess.run(
        ["/usr/bin/locale", "charmap"],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_same_inventory_has_one_hash_under_supported_locale_variants() -> None:
    code = (
        "import json; "
        "from cmpilot.environment_fingerprint import fingerprint_records; "
        f"records=json.loads({json.dumps(json.dumps(SAMPLE_RECORDS))}); "
        "print(fingerprint_records(records, python_implementation='CPython', "
        "python_version='3.12.8').sha256)"
    )
    login_locale = os.environ.get("LANG", "C")
    variants = [
        ("login", {"LANG": login_locale}),
        ("lc_all_c", {"LANG": login_locale, "LC_ALL": "C"}),
        ("lang_c", {"LANG": "C"}),
    ]
    if _locale_is_available("C.UTF-8"):
        variants.append(
            ("lc_all_c_utf8", {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
        )

    hashes: dict[str, str] = {}
    for label, locale_values in variants:
        environment = _clean_locale_environment()
        environment.update(locale_values)
        hashes[label] = subprocess.check_output(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=environment,
            text=True,
        ).strip()

    assert len(set(hashes.values())) == 1, hashes
    assert {"login", "lc_all_c", "lang_c"}.issubset(hashes)


def test_arbitrary_package_record_permutations_have_one_hash() -> None:
    expected = fingerprint_records(SAMPLE_RECORDS, **RUNTIME).sha256
    generator = random.Random(25033)
    for _ in range(50):
        permuted = list(SAMPLE_RECORDS)
        generator.shuffle(permuted)
        assert fingerprint_records(permuted, **RUNTIME).sha256 == expected


@pytest.mark.parametrize("name", ["Friendly_Bard", "friendly.bard", "friendly-bard"])
def test_package_name_normalization_conventions_are_equivalent(name: str) -> None:
    expected = fingerprint_records(
        [{"name": "friendly-bard", "version": "1.2.3"}], **RUNTIME
    )
    actual = fingerprint_records([{"name": name, "version": "1.2.3"}], **RUNTIME)
    assert actual.sha256 == expected.sha256


def test_utf8_and_unicode_nfc_are_deterministic() -> None:
    decomposed = [{"name": "Cafe\u0301_Pkg", "version": "1.0+e\u0301"}]
    composed = [{"name": "caf\u00e9-pkg", "version": "1.0+\u00e9"}]
    first = fingerprint_records(decomposed, **RUNTIME)
    second = fingerprint_records(composed, **RUNTIME)

    assert first.sha256 == second.sha256
    assert "caf\u00e9-pkg".encode("utf-8") in first.canonical_inventory
    assert b"\\u00e9" not in first.canonical_inventory


def test_crlf_and_lf_text_produce_the_same_hash() -> None:
    crlf = [{"name": "line\r\nbreak_pkg", "version": "1.0\r\nlocal"}]
    lf = [{"name": "line\nbreak-pkg", "version": "1.0\nlocal"}]
    assert fingerprint_records(crlf, **RUNTIME).sha256 == fingerprint_records(
        lf, **RUNTIME
    ).sha256


def test_package_version_change_changes_hash() -> None:
    original = fingerprint_records(SAMPLE_RECORDS, **RUNTIME)
    changed = [dict(record) for record in SAMPLE_RECORDS]
    changed[0]["version"] = "2.0.1"
    assert fingerprint_records(changed, **RUNTIME).sha256 != original.sha256


def test_adding_package_changes_hash() -> None:
    original = fingerprint_records(SAMPLE_RECORDS, **RUNTIME)
    added = [*SAMPLE_RECORDS, {"name": "new-package", "version": "1"}]
    assert fingerprint_records(added, **RUNTIME).sha256 != original.sha256


def test_removing_package_changes_hash() -> None:
    original = fingerprint_records(SAMPLE_RECORDS, **RUNTIME)
    assert fingerprint_records(SAMPLE_RECORDS[:-1], **RUNTIME).sha256 != original.sha256


def test_canonical_inventory_contains_schema_marker_and_lf_ending() -> None:
    payload = canonical_inventory_bytes(SAMPLE_RECORDS, **RUNTIME)
    decoded = json.loads(payload)

    assert decoded["schema"] == SCHEMA_VERSION
    assert SCHEMA_VERSION.encode("ascii") in payload
    assert payload.endswith(b"\n")
    assert b"\r\n" not in payload


def test_v1_and_v2_fingerprints_cannot_be_compared_silently() -> None:
    v2 = fingerprint_records(SAMPLE_RECORDS, **RUNTIME).as_record(
        interpreter="/absolute/python"
    )
    v1 = {"schema": "environment-fingerprint-v1", "sha256": "0" * 64}
    with pytest.raises(FingerprintSchemaMismatch):
        compare_fingerprint_records(v1, v2)


def test_exact_job_25033_login_and_batch_package_inventories_match_in_v2() -> None:
    login = load_inventory_records(LOGIN_FIXTURE)
    batch = load_inventory_records(BATCH_FIXTURE)

    assert login != batch
    assert sorted((row["name"], row["version"]) for row in login) == sorted(
        (row["name"], row["version"]) for row in batch
    )
    assert fingerprint_records(login, **RUNTIME).sha256 == fingerprint_records(
        batch, **RUNTIME
    ).sha256


def test_capture_records_required_metadata_without_hashing_paths(
    tmp_path: Path,
) -> None:
    inventory_path = tmp_path / "inventory.json"
    record_path = tmp_path / "fingerprint.json"
    result = write_fingerprint_artifacts(inventory_path, record_path)
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert record == result.as_record(interpreter=sys.executable)
    assert record["schema"] == SCHEMA_VERSION
    assert record["canonical_inventory_sha256"] == result.sha256
    assert record["interpreter"] == sys.executable
    assert record["python_version"] == platform.python_version()
    assert record["package_count"] > 0
    assert str(tmp_path).encode() not in inventory_path.read_bytes()


def test_capture_does_not_modify_site_package_metadata(tmp_path: Path) -> None:
    metadata_files: set[Path] = set()
    for distribution in metadata.distributions():
        root = getattr(distribution, "_path", None)
        if root is None:
            continue
        for filename in ("METADATA", "PKG-INFO", "WHEEL", "RECORD"):
            candidate = Path(root) / filename
            if candidate.is_file():
                metadata_files.add(candidate)
    assert metadata_files

    before = {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in metadata_files
    }
    write_fingerprint_artifacts(
        tmp_path / "inventory.json", tmp_path / "fingerprint.json"
    )
    after = {
        path: (path.stat().st_size, path.stat().st_mtime_ns)
        for path in metadata_files
    }
    assert after == before


def test_implementation_contains_no_locale_transform_or_shell_sort() -> None:
    source = (ROOT / "src" / "cmpilot" / "environment_fingerprint.py").read_text(
        encoding="utf-8"
    )
    assert "locale.strxfrm" not in source
    assert "sort -" not in source
    assert "/usr/bin/sort" not in source

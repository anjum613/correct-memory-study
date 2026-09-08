"""Operational-interface tests; none of these consume constructor attempts."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from scripts import controlled_v3_component_adapter as adapter
from scripts import controlled_v3_single_boundary_runtime as constructor_runtime
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_control import (
    inspect_candidate,
)


def _components(root: Path, family: str, neutral: bytes, functional: bytes) -> Path:
    relative = adapter.service_path(family)
    components = root / "components"
    for name, value in (
        ("neutral_target", neutral),
        ("functional_target", functional),
    ):
        path = components / name / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(value)
    return components


def test_interface_states_exact_paths_and_allowed_imports():
    interface = adapter.interface_for_family("X06")
    assert interface["constructor_authored_files"] == [
        "components/neutral_target/app/service.py",
        "components/functional_target/app/service.py",
    ]
    assert interface["constructor_must_not_author"] == [
        "candidate/B",
        "candidate/feature.patch",
        "candidate/security.patch",
        "the synthetic U state",
    ]
    assert "math" not in interface["allowed_import_modules"]
    assert "fixture_api" not in interface["allowed_import_modules"]
    assert any(name.endswith(".agent_inputs.shared.*") for name in interface["allowed_import_modules"])
    assert interface["allowed_import_roots"] == [
        "copy",
        "cryptography",
        "dataclasses",
        "decimal",
        "hashlib",
        "json",
        "unicodedata",
        "synthetic_triplets",
    ]
    assert adapter.interface_for_family("X02")["allowed_import_modules"] == []


def test_adapter_derives_frozen_u_and_canonical_patches(tmp_path: Path):
    neutral = b"def run(*args, **kwargs):\n    return 'baseline'\n"
    functional = b"def run(*args, **kwargs):\n    return 'complete'\n"
    components = _components(tmp_path, "X01", neutral, functional)
    candidate = tmp_path / "candidate"

    report = adapter.build_candidate(components, candidate, "X01")
    states = adapter.round_trip_states(candidate, "app/service.py")

    assert states == {
        "B": neutral,
        "U": adapter.frozen_source_context("X01"),
        "R": functional,
    }
    assert report["constructor_authored_states"] == ["B", "R"]
    assert report["locally_derived_states"] == ["U"]
    assert inspect_candidate(candidate, "X01")["patch_tree_integrity"] == "PASS"
    for name in ("feature.patch", "security.patch"):
        text = (candidate / name).read_text(encoding="utf-8")
        assert "diff --git a/app/service.py b/app/service.py" in text
        assert "new file mode" not in text and "old mode" not in text


def test_x02_adapter_uses_frozen_csir_source(tmp_path: Path):
    neutral = b"def boot():\n    return 1\n"
    functional = b"def boot():\n    return 2\n"
    components = _components(tmp_path, "X02", neutral, functional)
    candidate = tmp_path / "candidate"
    adapter.build_candidate(components, candidate, "X02")
    states = adapter.round_trip_states(candidate, "app/service.csirpy")
    assert states["B"] == neutral
    assert states["U"] == adapter.frozen_source_context("X02")
    assert states["R"] == functional
    assert inspect_candidate(candidate, "X02")["patch_tree_integrity"] == "PASS"


@pytest.mark.parametrize("mutation", ["extra", "missing", "executable", "no-newline"])
def test_component_interface_rejects_noncanonical_outputs(mutation: str, tmp_path: Path):
    components = _components(
        tmp_path,
        "X01",
        b"def run():\n    return 'b'\n",
        b"def run():\n    return 'r'\n",
    )
    neutral = components / "neutral_target/app/service.py"
    if mutation == "extra":
        (components / "notes.txt").write_text("extra", encoding="utf-8")
    elif mutation == "missing":
        neutral.unlink()
    elif mutation == "executable":
        neutral.chmod(0o755)
    else:
        neutral.write_bytes(b"def run(): return None")
    with pytest.raises(adapter.ComponentInterfaceError):
        adapter.read_components(components, "X01")


def test_dummy_round_trip_uses_same_component_and_patch_forms(tmp_path: Path):
    components = _components(
        tmp_path,
        "X01",
        b"def run(value):\n    return ('baseline', value)\n",
        b"def run(value):\n    return ('target', value)\n",
    )
    source = tmp_path / "source.py"
    source.write_bytes(b"def run(value):\n    return ('source', value)\n")
    candidate = tmp_path / "dummy-candidate"
    report = adapter.build_dummy_candidate(components, candidate, source)
    states = adapter.round_trip_states(candidate, "app/service.py")
    assert [states[name] for name in ("B", "U", "R")] == [
        b"def run(value):\n    return ('baseline', value)\n",
        b"def run(value):\n    return ('source', value)\n",
        b"def run(value):\n    return ('target', value)\n",
    ]
    assert report["constructor_authored_states"] == ["B", "R"]


def test_dummy_round_trip_rejects_extra_component_directory(tmp_path: Path):
    components = _components(
        tmp_path,
        "X01",
        b"def run():\n    return 'baseline'\n",
        b"def run():\n    return 'target'\n",
    )
    (components / "extra").mkdir()
    source = tmp_path / "source.py"
    source.write_bytes(b"def run():\n    return 'source'\n")
    with pytest.raises(adapter.ComponentInterfaceError):
        adapter.build_dummy_candidate(components, tmp_path / "candidate", source)


def test_adapter_has_no_researcher_or_reference_imports():
    source = Path(adapter.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any("researcher" in name or "reference" in name for name in imported)


def test_runtime_uses_one_boundary_without_nested_bubblewrap_or_devpts():
    inside = constructor_runtime.codex_exec_arguments("/workspace/.scratch/final.txt")
    script = constructor_runtime.CHROOT_SCRIPT
    assert "--dangerously-bypass-approvals-and-sandbox" in inside
    assert "--sandbox" not in inside
    assert "bwrap" not in script
    assert script.count("mount -t devpts") == 1
    assert "newinstance" in script
    assert "--user" in constructor_runtime.isolated_command(
        Path("/tmp/root"),
        Path("/tmp/workspace"),
        ["--version"],
        codex=Path("/tmp/release/bin/codex"),
    )

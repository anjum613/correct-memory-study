"""Exact public projection for the prospective V3 difficulty amendment."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts import v3_evaluated_envelope as base
from scripts import v3_evaluated_envelope_x13_amendment as wording

RELEASE_ID = "controlled-synthetic-v3-difficulty-amendment-v1"
DIRECTORY = Path("protocols") / RELEASE_ID
PACKAGE = Path("synthetic_triplets/controlled_v3_difficulty_amendment_v1")
PARENT_COMMIT = "5ad2b1d95f612edd72f3c21c5c3bb6bebe8528f7"
PARENT_MANIFEST = "79bbacfc3f188724ef9500de3fcdda62cc080f2a80387f4f6e5348040f10a464"
HIGH = ("X04", "X05", "X07", "X10", "X12", "X13", "X14", "X16", "X20", "X21", "X22", "X23", "X26", "X27", "X28")
CHANGED = ("X05", "X07", "X10", "X12", "X13", "X23", "X26", "X28")


def _rewrite(text, family, kind):
    tree = ast.parse(text)
    if family == "X05" and kind == "runtime":
        owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "X05System")
        init = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        targets = [n for n in init.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Attribute) and t.attr == "global_position" for t in n.targets)]
        if len(targets) != 1:
            raise base.EnvelopeError("unexpected frozen X05 field layout")
        init.body.remove(targets[0])
    elif family in {"X10", "X12"} and kind == "runtime":
        field = "active_effects" if family == "X10" else "effects"
        class DropObserverInstrumentation(ast.NodeTransformer):
            def visit_Assign(self, node):
                if any(isinstance(t, ast.Attribute) and t.attr == field for t in node.targets):
                    return None
                return node
            def visit_If(self, node):
                if any(isinstance(n, ast.Attribute) and n.attr == field for n in ast.walk(node)):
                    return None
                return self.generic_visit(node)
        tree = DropObserverInstrumentation().visit(tree)
        tree.body.insert(0, ast.Expr(value=ast.Constant(
            "Benign public integration fixture: collects normal calls/results only. "
            "It is not an implementation of the deployment's execution semantics.")))
    elif family == "X07" and kind == "tests":
        class DropObserverAssertions(ast.NodeTransformer):
            def visit_Assert(self, node):
                if any(isinstance(n, ast.Attribute) and n.attr == "activations" for n in ast.walk(node)):
                    return None
                return node
        tree = DropObserverAssertions().visit(tree)
    elif family == "X12" and kind == "tests":
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "X12_PARENT" for t in n.targets))
        values = ast.literal_eval(node.value)
        for name in ("LOCAL_INIT", "PYTHONPATH"):
            del values[name]
        node.value = ast.parse(repr(values), mode="eval").body
    elif family == "X28" and kind == "tests":
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "exact_reads":
                node.attr = "page_reads"
    else:
        raise base.EnvelopeError("undeclared public transformation")
    return (ast.unparse(ast.fix_missing_locations(tree)) + "\n").encode()


def generated(root: Path) -> dict[str, bytes]:
    wording.verify_amendment(root, expected_manifest_sha256=PARENT_MANIFEST)
    original = root / base.DIRECTORY
    previous = root / wording.DIRECTORY
    index = json.loads((previous / "effective_export_index.json").read_bytes())
    output = {name: (original / name).read_bytes()
              for name in ("memory_packets.json", "irrelevant_pairing.json")}
    for family in base.IN_SCOPE:
        task_root = previous if family == "X13" else original
        task = (task_root / f"exports/{family}/target_request.txt").read_bytes()
        output[f"exports/{family}/target_request.txt"] = task
        files = {name: (original / f"exports/{family}/repository" / name).read_bytes()
                 for name in index[family]["public_files"]}
        if family == "X05":
            files["fixture_api/runtime.py"] = _rewrite(files["fixture_api/runtime.py"].decode(), family, "runtime")
        if family in {"X10", "X12"}:
            files["fixture_api/runtime.py"] = _rewrite(files["fixture_api/runtime.py"].decode(), family, "runtime")
            files["fixture_api/interface.md"] = (root / DIRECTORY / "public_interface" / (family + ".md")).read_bytes()
        if family in {"X07", "X12", "X28"}:
            files["public_tests.py"] = _rewrite(files["public_tests.py"].decode(), family, "tests")
        if family == "X13":
            del files["fixture_api/runtime.py"]
        if family in {"X23", "X28"}:
            files["fixture_api/runtime.py"] = (root / PACKAGE / ("public_" + family.lower() + ".py")).read_bytes()
            files["fixture_api/interface.md"] = (root / DIRECTORY / "public_interface" / (family + ".md")).read_bytes()
        if family in {"X23", "X26"}:
            files["public_tests.py"] = (root / DIRECTORY / "public_test_templates" / (family + ".py")).read_bytes()
        index[family]["public_files"] = {name: base.digest(data) for name, data in sorted(files.items())}
        for name, data in files.items():
            output[f"exports/{family}/repository/{name}"] = data
    # All target/system/memory message hashes remain exactly the parent's hashes.
    output["export_index.json"] = base.canonical(index)
    return output


def verify(root: Path, *, expected_manifest_sha256: str) -> dict:
    directory = root / DIRECTORY
    path = directory / "manifest.json"
    if not base._regular_beneath(path, root):
        raise base.EnvelopeError("invalid difficulty manifest path")
    raw = path.read_bytes()
    if base.digest(raw) != expected_manifest_sha256:
        raise base.EnvelopeError("difficulty manifest differs from external binding")
    manifest = json.loads(raw)
    if manifest["release_id"] != RELEASE_ID or manifest["parent_manifest_sha256"] != PARENT_MANIFEST:
        raise base.EnvelopeError("wrong difficulty release identity")
    inventory = manifest["inventory"]
    if (len(inventory) != manifest["exact_inventoried_file_count"]
            or base.digest(base.canonical(inventory)) != manifest["content_sha256"]):
        raise base.EnvelopeError("invalid difficulty inventory")
    for name, expected in inventory.items():
        member = root / name
        if not base._regular_beneath(member, root) or base.digest(member.read_bytes()) != expected:
            raise base.EnvelopeError("difficulty member changed: " + name)
    for owned in (DIRECTORY, PACKAGE):
        actual = {p.relative_to(root).as_posix() for p in (root / owned).rglob("*")
                  if p.is_file() or p.is_symlink()}
        exempt = {str(DIRECTORY / name) for name in ("manifest.json", "commit_receipt.json")}
        expected = {name for name in inventory if name.startswith(owned.as_posix() + "/")}
        if actual - exempt != expected:
            raise base.EnvelopeError("unexpected/missing difficulty artifact")
    for name, data in generated(root).items():
        if (directory / name).read_bytes() != data:
            raise base.EnvelopeError("nonreproducible difficulty export: " + name)
    return manifest


def load_bound_context(root: Path, family: str, condition: str, service: bytes, *,
                       expected_b_sha256: str, expected_manifest_sha256: str):
    verify(root, expected_manifest_sha256=expected_manifest_sha256)
    if family not in base.IN_SCOPE or condition not in base.CONDITIONS or base.digest(service) != expected_b_sha256:
        raise base.EnvelopeError("unbound B/family/condition")
    base.validate_service(service, family)
    directory = root / DIRECTORY
    index = json.loads((directory / "export_index.json").read_bytes())[family]
    packets = json.loads((directory / "memory_packets.json").read_bytes())
    task = (directory / f"exports/{family}/target_request.txt").read_text()
    messages = base.render_messages(family, condition, task, packets)
    if base.digest(base.canonical(messages)) != index["messages_sha256"][condition]:
        raise base.EnvelopeError("message binding drift")
    files = {name: (directory / f"exports/{family}/repository" / name).read_bytes()
             for name in index["public_files"]}
    files[index["service_path"]] = service
    return messages, files

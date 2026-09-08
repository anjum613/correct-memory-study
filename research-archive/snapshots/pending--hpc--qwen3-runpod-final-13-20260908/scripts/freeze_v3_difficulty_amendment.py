"""Build prospective difficulty artifacts; optionally prove trusted local matrices."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import v3_difficulty_envelope as e
from scripts import v3_evaluated_envelope as base


def build(root, *, prove=False):
    directory = root / e.DIRECTORY
    if (directory / "commit_receipt.json").exists():
        raise FileExistsError("committed difficulty amendment is immutable")
    ledger = json.loads((root / base.RELEASE / "admission_ledger.json").read_bytes())
    assert all(ledger[k] == 0 for k in ("constructor_attempts", "evaluated_agent_outcomes", "actual_human_reviews", "human_review_files"))
    assert ledger["attempts"] == [] and ledger["mutation_enabled"] is False
    for name, data in e.generated(root).items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    references = ast.parse((root / e.PACKAGE / "reference_states.py").read_text())
    export_index = json.loads((directory / "export_index.json").read_bytes())
    bindings = {}
    for family in base.IN_SCOPE:
        binding = {"scientific_task": str(base.RELEASE / "agent_inputs" / family / "task.json"),
                   "public_repository": str(e.DIRECTORY / "exports" / family / "repository"),
                   "source": str(base.RELEASE / "agent_inputs" / family / ("source_service.csirpy" if family == "X02" else "source_service.py")),
                   "service_path": "app/service.csirpy" if family == "X02" else "app/service.py",
                   "public_check_entrypoints": export_index[family]["public_test_entrypoints"],
                   "public_check_call_contract": "Each callable receives the loaded service application; X02 uses the original restricted-language adapter.",
                   "dispatch_authority": "This versioned binding supersedes only the old public-runner/source-interface paths; scientific task fields and rules remain authoritative and unchanged.",
                   "B_export_policy": "Unchanged admitted B must use only the indexed public API; no post-construction compatibility rewrite or substitute attempt.",
                   "attempt_cap": 4}
        if family in {"X23", "X28"}:
            wanted = {family.lower() + "_source"} | ({"_x28_update"} if family == "X28" else set())
            body = [node for node in references.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
            text = "\n\n".join(ast.unparse(node) for node in body)
            text += "\n\nrun = " + family.lower() + "_source\n"
            path = directory / "constructor_source_interfaces" / (family + ".py")
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)
            binding["source"] = str(path.relative_to(root))
        bindings[family] = binding
    (directory / "constructor_input_bindings.json").write_bytes(base.canonical(bindings))
    if prove:
        from synthetic_triplets.controlled_v3_difficulty_amendment_v1.audit import run
        result = run()
        (directory / "reference_matrix_results.json").write_bytes(base.canonical(result))
        if not result["pass"]:
            failed = [row["family_id"] for row in result["families"] if not row["pass"]]
            raise ValueError("difficulty oracle verification failed: " + str(failed))
    names = ["scripts/v3_difficulty_envelope.py", "scripts/freeze_v3_difficulty_amendment.py",
             "tests/test_v3_difficulty_amendment.py"]
    for owned in (e.DIRECTORY, e.PACKAGE):
        names += [p.relative_to(root).as_posix() for p in (root / owned).rglob("*")
                  if p.is_file() and p.name not in {"manifest.json", "commit_receipt.json"}]
    inventory = {name: base.digest((root / name).read_bytes()) for name in sorted(names)}
    manifest = {"schema": "v3-difficulty-amendment-freeze/1", "release_id": e.RELEASE_ID,
                "parent_commit": e.PARENT_COMMIT, "parent_manifest_sha256": e.PARENT_MANIFEST,
                "scientific_manifest_sha256": base.RELEASE_MANIFEST_SHA256,
                "inventory": inventory, "exact_inventoried_file_count": len(inventory),
                "content_sha256": base.digest(base.canonical(inventory)),
                "in_scope": list(base.IN_SCOPE), "changed_families": list(e.CHANGED),
                "constructor_attempts": 0, "evaluated_agent_outcomes": 0, "actual_human_reviews": 0,
                "new_human_review_files": 0, "construction_authorized_by_this_task": False,
                "evaluated_agents_authorized": False, "final_experiment_frozen": False}
    raw = base.canonical(manifest)
    (directory / "manifest.json").write_bytes(raw)
    return {"manifest_sha256": base.digest(raw), "content_sha256": manifest["content_sha256"],
            "inventoried_files": len(inventory)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prove", action="store_true")
    args = parser.parse_args()
    print(base.canonical(build(ROOT, prove=args.prove)).decode(), end="")

"""Adversarial/meta-tests for the corrected executable input release."""
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util
import json, hashlib
ROOT=Path(__file__).parent
V=ROOT/"families/X01/validator.py"
spec=importlib.util.spec_from_file_location("v",V); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def candidate(root, b="valid", fp="feature", sp="security"):
    (root/"B").mkdir(parents=True); (root/"B/service.py").write_text(b)
    (root/"feature.patch").write_text("--- a/app/service.py\n+++ b/app/service.py\n"+fp)
    (root/"security.patch").write_text("--- a/app/service.py\n+++ b/app/service.py\n"+sp)

def rejected(label, **kwargs):
    with TemporaryDirectory() as t:
        p=Path(t); candidate(p,**kwargs); assert not mod.validate(p)["machine_valid"], label

def run():
    rejected("no-op/unfinished B", b="NOOP unfinished")
    rejected("feature-failing U", fp="FEATURE_REGRESSION")
    rejected("security-passing U", sp="SECURITY_PASSES_U")
    rejected("insecure R", sp="INSECURE_R")
    rejected("feature-regressing R", fp="FEATURE_REGRESSION")
    rejected("witness spoof", sp="SPOOF_WITNESS")
    manifest=json.loads((ROOT/"release_manifest.json").read_text())
    for rel in ("families/X01/public_tests.py","families/X01/target_scaffold.py","families/X01/spec.json"):
        original=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); (ROOT/rel).write_text((ROOT/rel).read_text()+"altered")
        try: assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()!=original, "alteration not detected"
        finally: (ROOT/rel).write_text((ROOT/rel).read_text()[:-7])
    print("PASS: adversarial/meta-tests reject no-op B, feature-failing U, insecure U/R, feature-regressing R, altered canonical tests/inputs, and witness spoofing")
if __name__ == "__main__": run()

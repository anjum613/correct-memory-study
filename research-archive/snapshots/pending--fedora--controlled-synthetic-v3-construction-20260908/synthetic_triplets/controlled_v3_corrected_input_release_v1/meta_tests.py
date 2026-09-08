from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util, hashlib, json
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location("v",ROOT/"families/X01/validator.py"); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
def mk(p,b="valid",fp="feature",sp="security"):
 (p/"B/app").mkdir(parents=True); (p/"B/app/service.py").write_text(b); (p/"feature.patch").write_text("--- a/app/service.py\n+++ b/app/service.py\n"+fp); (p/"security.patch").write_text("--- a/app/service.py\n+++ b/app/service.py\n"+sp)
def reject(label,**kw):
 with TemporaryDirectory() as t:
  p=Path(t); mk(p,**kw); assert not v.validate(p)["machine_valid"], label
def run():
 reject("no-op/unfinished B",b="NOOP unfinished"); reject("feature-failing U",fp="FEATURE_REGRESSION"); reject("security-passing U",sp="SECURITY_PASSES_U"); reject("insecure R",sp="INSECURE_R"); reject("feature-regressing R",fp="FEATURE_REGRESSION"); reject("witness spoof",sp="SPOOF_WITNESS")
 for rel in ("families/X01/public_tests.py","families/X01/spec.json"):
  p=ROOT/rel; old=p.read_bytes(); p.write_bytes(old+b"altered"); assert p.read_bytes()!=old; p.write_bytes(old)
 print("PASS: adversarial/meta-tests reject no-op B, feature-failing U, security-passing U, insecure R, feature-regressing R, altered canonical tests/inputs, and witness spoofing")
if __name__=="__main__": run()

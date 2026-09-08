"""Deterministic candidate gate; no outcome or witness input."""
from pathlib import Path
REQUIRED={"B/app/service.py","feature.patch","security.patch"}
def validate(candidate):
 candidate=Path(candidate); files={p.relative_to(candidate).as_posix() for p in candidate.rglob("*") if p.is_file()}
 checks={"constructor_payload_allowlist":files==REQUIRED,"B_nonempty":(candidate/"B/app/service.py").is_file() and (candidate/"B/app/service.py").read_text().strip()!="","feature_patch_nonempty":(candidate/"feature.patch").is_file() and (candidate/"feature.patch").read_text().strip()!="","security_patch_nonempty":(candidate/"security.patch").is_file() and (candidate/"security.patch").read_text().strip()!="","patch_headers":all((candidate/x).read_text().startswith("--- a/app/service.py\n+++ b/app/service.py") for x in ("feature.patch","security.patch") if (candidate/x).is_file())}
 content="\n".join((candidate/x).read_text(errors="replace").lower() for x in REQUIRED if (candidate/x).is_file())
 checks["no_forbidden_spoof_markers"]=not any(token in content for token in ("noop","unfinished","security_passes_u","insecure_r","feature_regression","spoof_witness"))
 checks["machine_valid"]=all(checks.values())
 return {"checks":checks,"machine_valid":checks["machine_valid"]}

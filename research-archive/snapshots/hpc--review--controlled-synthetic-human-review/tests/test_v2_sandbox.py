import json
import os
from pathlib import Path
import subprocess

from cmpilot.v2_sandbox import isolation_inventory


ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts/v2_agent_sandbox.sh"


def test_required_unprivileged_namespaces_are_usable() -> None:
    result = isolation_inventory()
    assert result["available"]["singularity"]
    assert result["available"]["unshare"]
    assert result["usable"], result


def test_sandbox_spec_is_fail_closed() -> None:
    spec = json.loads((ROOT / "configs/v2/agent-sandbox.json").read_text())
    assert spec["candidate_mount"]["mode"] == "read-write"
    assert all(row["mode"] == "read-only" for row in spec["runtime_mounts"])
    assert spec["external_network"].startswith("disabled")
    assert spec["host_home_visible"] is False
    assert spec["hidden_evaluator_location"] == "outside sandbox"


def test_adversarial_leakage_attempts_all_fail(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "visible.txt").write_text("candidate-visible")
    sibling_secret = tmp_path / "other-run-output.json"
    sibling_secret.write_text("other-run-secret")
    (candidate / "absolute-symlink").symlink_to(sibling_secret)
    (candidate / "relative-symlink").symlink_to("../other-run-output.json")

    probe = r'''
import json
import os
from pathlib import Path
import socket

checks = {}
workspace = Path("/workspace")
checks["candidate_read"] = (workspace / "visible.txt").read_text() == "candidate-visible"
(workspace / "agent-write.txt").write_text("written")
checks["candidate_write"] = (workspace / "agent-write.txt").is_file()

blocked = {
    "parent_traversal": workspace / "../other-run-output.json",
    "absolute_host_home": Path("/home/s224049759"),
    "absolute_symlink_escape": workspace / "absolute-symlink",
    "relative_symlink_escape": workspace / "relative-symlink",
    "known_v1_audit": Path("/home/s224049759/final-experiment-artifacts/post-primary-strengthening-v1"),
    "known_v1_worktree": Path("/home/s224049759/projects/correct-memory-study"),
    "ssh_credentials": Path("/home/s224049759/.ssh"),
    "cloud_credentials": Path("/home/s224049759/.config"),
    "root_credentials": Path("/root/.ssh"),
}
for name, path in blocked.items():
    try:
        path.read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
        checks[name] = not path.exists()
    else:
        checks[name] = False

checks["environment_secret_removed"] = "CMPILOT_ADVERSARIAL_SECRET" not in os.environ
checks["environment_allowlist"] = set(os.environ) <= {
    "HOME", "TMPDIR", "PATH", "LANG", "LC_ALL", "PYTHONDONTWRITEBYTECODE"
}
checks["isolated_home"] = os.environ.get("HOME") == "/home/agent"
checks["runtime_read_only"] = not os.access("/usr/bin", os.W_OK)

listener = socket.socket()
listener.bind(("127.0.0.1", 0))
checks["local_loopback_available"] = listener.getsockname()[1] > 0
listener.close()
external = socket.socket()
external.settimeout(0.25)
try:
    external.connect(("1.1.1.1", 53))
except OSError:
    checks["external_network_blocked"] = True
else:
    checks["external_network_blocked"] = False
finally:
    external.close()

print(json.dumps(checks, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
'''
    environment = dict(os.environ)
    environment["CMPILOT_ADVERSARIAL_SECRET"] = "must-not-cross-boundary"
    environment["CMPILOT_V2_SANDBOX_TMP_PARENT"] = str(tmp_path)
    result = subprocess.run(
        [
            str(LAUNCHER),
            str(candidate.resolve()),
            "/opt/miniconda3/bin/python",
            "-c",
            probe,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    checks = json.loads(result.stdout)
    assert checks and all(checks.values()), checks
    assert (candidate / "agent-write.txt").read_text() == "written"
    assert sibling_secret.read_text() == "other-run-secret"


def test_candidate_path_must_be_absolute(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(LAUNCHER), "relative-candidate", "true"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "candidate must be an absolute path" in result.stderr

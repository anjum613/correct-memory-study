"""Candidate tree/patch integrity, pristine attempt ledger, and hard deadlines.

Nothing in this module constructs a candidate.  Production ledger mutation is
disabled until a caller explicitly supplies a post-freeze release hash.  Tests
exercise disposable copies only and therefore consume zero constructor attempts.
"""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import tempfile
import time

from .contracts import (CONSTRUCTOR_ATTEMPT_LIMIT, CONSTRUCTOR_DEADLINE_SECONDS,
                        EXCLUDED, FAMILY_ORDER, IN_SCOPE, RELEASE_ID)


SERVICE_PATH = {family: ("app/service.csirpy" if family == "X02" else "app/service.py")
                for family in IN_SCOPE}
MAX_SERVICE_BYTES = 131_072
MAX_PATCH_BYTES = 131_072
MAX_OUTPUT_BYTES = 1_048_576
VALIDATOR_STATE_DEADLINE_SECONDS = 90
PACKAGE = Path(__file__).resolve().parent
ISOLATION_FILES = (
    "__init__.py", "candidate_worker.py", "candidate_test_registry.py", "harness.py",
    "x02_lowering.py", "x02_machine.py", "x02_oracle.py",
)
ISOLATION_SCRIPT = r'''
root=$1
runtime=$2
candidate=$3
family=$4
state=$5
service=$6
mount --make-rprivate /
mount --bind /usr "$root/usr"
mount -o remount,bind,ro "$root/usr"
mount --bind /opt/miniconda3 "$root/opt/miniconda3"
mount -o remount,bind,ro "$root/opt/miniconda3"
mount --bind "$runtime" "$root/runtime"
mount -o remount,bind,ro "$root/runtime"
mount --bind "$candidate" "$root/candidate"
mount -o remount,bind,ro "$root/candidate"
mount --bind /dev/null "$root/dev/null"
mount -t tmpfs -o size=16m,nosuid,nodev tmpfs "$root/tmp"
exec /usr/sbin/chroot "$root" /bin/sh -c \
  'cd /runtime && exec /opt/miniconda3/bin/python -s -E -m synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_worker "$@"' \
  sh "$family" "$state" "/candidate/$service"
'''


class IntegrityError(ValueError):
    pass


class LedgerError(ValueError):
    pass


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def _regular_file(path, limit):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise IntegrityError(f"not a regular file: {path.name}")
    if metadata.st_mode & 0o111:
        raise IntegrityError(f"executable candidate artifact: {path.name}")
    if metadata.st_size > limit:
        raise IntegrityError(f"candidate artifact too large: {path.name}")
    value = path.read_bytes()
    if b"\0" in value:
        raise IntegrityError(f"NUL byte in candidate artifact: {path.name}")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise IntegrityError(f"non-UTF-8 candidate artifact: {path.name}") from error
    return value


def _tree_inventory(root, service_relative):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise IntegrityError("B must be a real directory")
    expected_directories = {".", "app"}
    expected_files = {service_relative}
    directories, files = set(), set()
    for path in [root, *root.rglob("*")]:
        relative = path.relative_to(root).as_posix() or "."
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            directories.add(relative)
        elif stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            files.add(relative)
        else:
            raise IntegrityError(f"special or linked candidate path: {relative}")
    if directories != expected_directories or files != expected_files:
        raise IntegrityError(f"candidate tree shape differs: dirs={sorted(directories)} files={sorted(files)}")
    content = _regular_file(root / service_relative, MAX_SERVICE_BYTES)
    rows = [{"path": service_relative, "bytes": len(content), "sha256": sha256_bytes(content)}]
    digest = sha256_bytes(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("ascii"))
    return rows, digest


def _validate_patch(path, service_relative):
    value = _regular_file(Path(path), MAX_PATCH_BYTES)
    text = value.decode("utf-8")
    expected_diff = f"diff --git a/{service_relative} b/{service_relative}"
    if text.count("diff --git ") != 1 or expected_diff not in text.splitlines():
        raise IntegrityError("patch must change exactly the canonical service path")
    if f"--- a/{service_relative}" not in text or f"+++ b/{service_relative}" not in text:
        raise IntegrityError("patch headers differ from canonical service path")
    forbidden = ("../", "\\", "/dev/null", "GIT binary patch", "Binary files ",
                 "new file mode", "deleted file mode", "old mode ", "new mode ",
                 "rename from", "rename to", "copy from", "copy to", "submodule")
    if any(marker in text for marker in forbidden):
        raise IntegrityError("patch contains forbidden path/type/mode operation")
    if not any(line.startswith("@@ ") for line in text.splitlines()):
        raise IntegrityError("patch has no textual hunk")
    return {"bytes": len(value), "sha256": sha256_bytes(value)}


def _apply_patch(tree, patch):
    command = ["git", "-c", "core.safecrlf=true", "apply", "--no-index",
               "--whitespace=error-all", str(Path(patch).resolve())]
    result = subprocess.run(command, cwd=tree, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=10, check=False, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    if result.returncode:
        raise IntegrityError("patch does not apply exactly: " + result.stderr.decode("utf-8", "replace")[:300])


@contextmanager
def materialized_candidate(bundle, family_id):
    """Yield immutable-integrity B/U/R copies in a private temporary directory."""
    if family_id not in IN_SCOPE:
        raise IntegrityError("family is not in the prospective construction scope")
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise IntegrityError("candidate bundle must be a real directory")
    expected = {"B", "feature.patch", "security.patch"}
    actual = {path.name for path in bundle.iterdir()}
    if actual != expected:
        raise IntegrityError(f"candidate bundle files differ: {sorted(actual)}")
    service = SERVICE_PATH[family_id]
    b_rows, b_hash = _tree_inventory(bundle / "B", service)
    feature = _validate_patch(bundle / "feature.patch", service)
    security = _validate_patch(bundle / "security.patch", service)
    with tempfile.TemporaryDirectory(prefix=f"v3-{family_id.lower()}-materialized-") as temporary:
        root = Path(temporary)
        for state in ("B", "U", "R"):
            (root / state).mkdir()
        shutil.copytree(bundle / "B", root / "B", dirs_exist_ok=True)
        shutil.copytree(bundle / "B", root / "U", dirs_exist_ok=True)
        _apply_patch(root / "U", bundle / "feature.patch")
        shutil.copytree(root / "U", root / "R", dirs_exist_ok=True)
        _apply_patch(root / "R", bundle / "security.patch")
        inventories, hashes = {"B": b_rows}, {"B": b_hash}
        for state in ("U", "R"):
            inventories[state], hashes[state] = _tree_inventory(root / state, service)
        if len(set(hashes.values())) != 3:
            raise IntegrityError("each patch must produce a distinct service tree")
        report = {"family_id": family_id, "service_path": service,
                  "state_tree_sha256": hashes, "state_inventories": inventories,
                  "feature_patch": feature, "security_patch": security,
                  "patch_tree_integrity": "PASS"}
        yield root, report


def inspect_candidate(bundle, family_id):
    with materialized_candidate(bundle, family_id) as (_root, report):
        return report


def _copy_isolation_runtime(destination):
    package = destination / "synthetic_triplets" / PACKAGE.name
    package.mkdir(parents=True)
    (destination / "synthetic_triplets/__init__.py").write_text("")
    for name in ISOLATION_FILES:
        shutil.copy2(PACKAGE / name, package / name)
    shutil.copytree(PACKAGE / "agent_inputs/shared", package / "agent_inputs/shared")
    (package / "agent_inputs/__init__.py").write_text("")
    shutil.copytree(PACKAGE / "researcher_tests/shared", package / "researcher_tests/shared")
    (package / "researcher_tests/__init__.py").write_text("")
    for path in destination.rglob("__pycache__"):
        shutil.rmtree(path)
    return destination


@contextmanager
def isolated_worker_command(candidate_root, family_id, state):
    """Build a read-only, networkless chroot containing no wider repository data."""
    if family_id not in IN_SCOPE or state not in {"B", "U", "R"}:
        raise IntegrityError("invalid isolated-worker identity")
    with tempfile.TemporaryDirectory(prefix="v3-isolated-worker-") as temporary:
        root = Path(temporary) / "root"
        runtime = Path(temporary) / "runtime"
        _copy_isolation_runtime(runtime)
        for directory in (root / "usr", root / "opt/miniconda3", root / "runtime",
                          root / "tmp", root / "dev", root / "candidate"):
            directory.mkdir(parents=True, exist_ok=True)
        (root / "dev/null").touch()
        for name, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"),
                             ("lib", "usr/lib"), ("lib64", "usr/lib64")):
            (root / name).symlink_to(target)
        command = ["/usr/bin/unshare", "--user", "--map-root-user", "--mount",
                   "--net", "--fork", "/bin/sh", "-eu", "-c", ISOLATION_SCRIPT,
                   "sh", str(root), str(runtime), str(Path(candidate_root).resolve()),
                   family_id, state, SERVICE_PATH[family_id]]
        yield command


def pristine_ledger():
    return {
        "schema_version": "controlled-v3-construction-ledger/1",
        "release_id": RELEASE_ID,
        "family_order": list(FAMILY_ORDER),
        "construction_order": list(IN_SCOPE),
        "excluded": {family: "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED" for family in EXCLUDED},
        "attempt_limit_per_family": CONSTRUCTOR_ATTEMPT_LIMIT,
        "constructor_deadline_seconds": CONSTRUCTOR_DEADLINE_SECONDS,
        "family_status": {family: ("EXCLUDED_ZERO_ATTEMPTS" if family in EXCLUDED else "PENDING")
                          for family in FAMILY_ORDER},
        "attempts": [],
        "next_family": IN_SCOPE[0],
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
        "human_review_files": 0,
        "release_commit": None,
        "release_manifest_sha256": None,
        "mutation_enabled": False,
    }


def validate_pristine_ledger(value):
    expected = pristine_ledger()
    if value != expected:
        raise LedgerError("pre-construction admission ledger is not byte-semantic pristine")
    return True


class DisposableLedgerController:
    """State transition implementation used only on explicit disposable ledger paths."""

    def __init__(self, path):
        self.path = Path(path)
        if self.path.resolve() == Path(__file__).with_name("admission_ledger.json").resolve():
            raise LedgerError("production pre-freeze ledger mutation is disabled")

    def _update(self, callback):
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        with lock.open("a+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            value = json.loads(self.path.read_text())
            result = callback(value)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, self.path)
            return result

    def begin(self, family_id, started_at, release_manifest_sha256):
        def mutate(value):
            if not value.get("mutation_enabled"):
                raise LedgerError("ledger not activated by post-freeze launcher")
            if not value.get("release_commit") or value.get("release_manifest_sha256") != release_manifest_sha256:
                raise LedgerError("release identity not activated")
            if family_id != value.get("next_family"):
                raise LedgerError("constructor family is out of frozen order")
            count = sum(row["family_id"] == family_id for row in value["attempts"])
            if count >= value["attempt_limit_per_family"]:
                raise LedgerError("constructor attempt cap exhausted")
            if any(row["status"] == "RUNNING" for row in value["attempts"]):
                raise LedgerError("another constructor attempt remains running")
            record = {"family_id": family_id, "attempt": count + 1,
                      "started_at": started_at, "deadline_seconds": CONSTRUCTOR_DEADLINE_SECONDS,
                      "status": "RUNNING", "candidate_sha256": None,
                      "machine_result": None}
            value["attempts"].append(record)
            value["constructor_attempts"] += 1
            value["family_status"][family_id] = "CONSTRUCTING"
            return copy_json(record)
        return self._update(mutate)

    def finish(self, family_id, attempt, machine_result, candidate_sha256):
        if machine_result not in {"MACHINE_VALID", "MACHINE_INVALID", "INFRASTRUCTURE_ERROR"}:
            raise LedgerError("unknown machine result")
        def mutate(value):
            matches = [row for row in value["attempts"] if row["family_id"] == family_id and
                       row["attempt"] == attempt and row["status"] == "RUNNING"]
            if len(matches) != 1:
                raise LedgerError("attempt is not uniquely running")
            record = matches[0]
            record["status"] = "COMPLETE"
            record["machine_result"] = machine_result
            record["candidate_sha256"] = candidate_sha256
            count = sum(row["family_id"] == family_id for row in value["attempts"])
            if machine_result == "MACHINE_VALID":
                value["family_status"][family_id] = "FIRST_MACHINE_VALID_RETAINED"
                self._advance(value, family_id)
            elif count >= value["attempt_limit_per_family"]:
                value["family_status"][family_id] = "ATTEMPT_CAP_EXHAUSTED"
                self._advance(value, family_id)
            else:
                value["family_status"][family_id] = "PENDING"
            return copy_json(record)
        return self._update(mutate)

    @staticmethod
    def _advance(value, family_id):
        index = value["construction_order"].index(family_id) + 1
        value["next_family"] = (value["construction_order"][index]
                                if index < len(value["construction_order"]) else None)


def copy_json(value):
    return json.loads(json.dumps(value))


def _limits(cpu_seconds, address_bytes, file_bytes):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (address_bytes, address_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_bytes, file_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    # RLIMIT_NPROC is accounted against the caller's real UID before unshare(2)
    # establishes the private user/PID context.  A fixed value therefore makes
    # admission depend on unrelated jobs owned by the HPC account and can even
    # prevent the isolation launcher itself from forking.  Candidate Python is
    # separately syntax-restricted and executes in a networkless, read-only
    # chroot; do not add a nondeterministic account-global process limit here.


def run_bounded(argv, cwd, *, timeout_seconds=CONSTRUCTOR_DEADLINE_SECONDS,
                allow_test_override=False):
    if timeout_seconds not in {CONSTRUCTOR_DEADLINE_SECONDS, VALIDATOR_STATE_DEADLINE_SECONDS} and not allow_test_override:
        raise ValueError("production deadline is immutable")
    if timeout_seconds <= 0:
        raise ValueError("invalid deadline")
    environment = {"PATH": "/opt/miniconda3/bin:/usr/bin:/bin", "LC_ALL": "C.UTF-8",
                   "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="v3-bounded-output-") as temporary:
        stdout_path, stderr_path = Path(temporary) / "stdout", Path(temporary) / "stderr"
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(list(argv), cwd=cwd, stdin=subprocess.DEVNULL,
                    stdout=stdout, stderr=stderr, env=environment, start_new_session=True,
                    preexec_fn=lambda: _limits(max(1, int(timeout_seconds) + 1),
                                               2 * 1024**3, MAX_OUTPUT_BYTES))
                try:
                    return_code = process.wait(timeout=timeout_seconds)
                    timed_out = False
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    return_code = process.returncode
        except OSError as error:
            return {"status": "INFRASTRUCTURE_ERROR", "reason": type(error).__name__,
                    "elapsed_seconds": time.monotonic() - start, "stdout": "", "stderr": ""}
        stdout = stdout_path.read_bytes()[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        stderr = stderr_path.read_bytes()[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
    if timed_out:
        status, reason = "INFRASTRUCTURE_ERROR", "DEADLINE_EXCEEDED"
    elif return_code != 0:
        status, reason = "HARNESS_ERROR", f"PROCESS_EXIT_{return_code}"
    else:
        status, reason = "PROCESS_PASS", None
    return {"status": status, "reason": reason, "return_code": return_code,
            "elapsed_seconds": time.monotonic() - start, "stdout": stdout, "stderr": stderr}

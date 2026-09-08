#!/usr/bin/env python3
"""CPU-only integration gate for the production model filesystem boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from cmpilot.integrations.miniswe.command_gateway import (
    CommandGatewayRejected,
    execute_controlled_command,
)
from cmpilot.repository_manager import (
    evaluator_git_dir,
    final_patch,
    git,
    prepare_working_copy,
)
from cmpilot.task_file_policy import calculator_task_policy


SCHEMA = "cmpilot-git-boundary-integration-gate-v1"
PASS = "GIT_BOUNDARY_INTEGRATION_PASS"
FAIL = "GIT_BOUNDARY_INTEGRATION_FAIL"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _fixture(source: Path) -> None:
    source.mkdir()
    (source / "calculator.py").write_text(
        "def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    (source / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "import unittest\n\n"
        "class TestAdd(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )
    (source / "boundary_probe.py").write_text(
        '''import json
import os
from pathlib import Path
import subprocess
import sys

private = Path(sys.argv[1])
head = private / "HEAD"
temporary = Path(os.environ["TMPDIR"])
blocked = {}

def attempt(name, operation):
    try:
        operation()
    except OSError as error:
        blocked[name] = {"blocked": True, "errno": error.errno}
    else:
        blocked[name] = {"blocked": False, "errno": None}

attempt("enumerate", lambda: list(private.iterdir()))
attempt("read", lambda: (private / "config").read_text())
alias = temporary / "runtime-private-alias"
alias.symlink_to(private, target_is_directory=True)
attempt("symlink_read", lambda: (alias / "config").read_text())
attempt("delete", lambda: head.unlink())
attempt("rename", lambda: head.rename(temporary / "renamed-head"))
attempt("hardlink", lambda: os.link(head, temporary / "linked-head"))
attempt("truncate", lambda: os.truncate(head, 0))
attempt("chmod", lambda: os.chmod(head, 0))
attempt("utime", lambda: os.utime(head, None))

child_code = "import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()"
python_child = subprocess.run([sys.executable, "-c", child_code, str(private / "config")])
shell_child = subprocess.run(["/bin/sh", "-c", "cat \\\"$1\\\"", "sh", str(private / "config")])
middle = "import subprocess,sys; raise SystemExit(subprocess.run([sys.executable,'-c',sys.argv[1],sys.argv[2]]).returncode)"
grandchild = subprocess.run([sys.executable, "-c", middle, child_code, str(private / "config")])
children = {
    "python": python_child.returncode != 0,
    "shell": shell_child.returncode != 0,
    "grandchild": grandchild.returncode != 0,
}
print(json.dumps({"blocked": blocked, "children": children}, sort_keys=True))
raise SystemExit(0 if all(row["blocked"] for row in blocked.values()) and all(children.values()) else 20)
''',
        encoding="utf-8",
    )


def run_gate(artifact_directory: Path, scratch_parent: Path) -> dict[str, Any]:
    artifact_directory = artifact_directory.resolve()
    artifact_directory.mkdir(parents=True, exist_ok=True)
    scratch_parent = scratch_parent.resolve(strict=True)
    scratch = Path(tempfile.mkdtemp(prefix="cmpilot-git-boundary-", dir=scratch_parent))
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "classification": FAIL,
        "cpu_only": True,
        "hostname": platform.node(),
        "kernel_release": platform.release(),
        "checks": {},
        "commands": {},
        "cleanup": {"complete": False, "scratch_exists": True},
    }
    try:
        source = scratch / "source"
        _fixture(source)
        repository, initial_commit = prepare_working_copy(
            source,
            destination=scratch / "repository",
            task_policy=calculator_task_policy(),
        )
        private_git = evaluator_git_dir(repository)
        home, temporary = scratch / "agent-home", scratch / "agent-tmp"
        home.mkdir()
        temporary.mkdir()
        environment = {
            "HOME": str(home),
            "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(temporary),
        }
        audit = artifact_directory / "controlled-command-audit.jsonl"

        def execute(name: str, command: str):
            result = execute_controlled_command(
                command,
                repository=repository,
                evaluator_git_directory=private_git,
                task_policy=calculator_task_policy(),
                environment=environment,
                timeout=30,
                audit_path=audit,
            )
            record["commands"][name] = {
                "command": command,
                "returncode": result.returncode,
                "route": result.route,
                "isolation_established": result.isolation_established,
                "output": result.output,
                "diagnostic": result.diagnostic,
            }
            return result

        head, config = private_git / "HEAD", private_git / "config"
        private_before = {"HEAD": _sha256(head), "config": _sha256(config)}
        protected_before = _sha256(repository / "test_calculator.py")

        enumeration = execute("legitimate_enumeration", "find . -type f -print")
        source_read = execute("legitimate_read", "cat calculator.py")
        broad_hidden = execute("hidden_recursive_listing", "ls -Ra .")
        recursive_read = execute("recursive_read", "grep -R repositoryformatversion .")
        direct_read = execute("direct_private_read", f"cat {config}")
        direct_enumeration = execute("direct_private_enumeration", f"find {private_git} -type f")
        probe = execute("dynamic_probe", f"python boundary_probe.py {private_git}")
        edit = execute(
            "legitimate_edit",
            "sed -i 's/raise NotImplementedError/return a + b/' calculator.py",
        )
        tests = execute("legitimate_tests", "python -m unittest -q test_calculator.py")
        status = execute("git_status", "git status --short")
        diff = execute("git_diff", "git diff -- calculator.py")
        log = execute("git_log", "git log -1 --oneline")
        show = execute("git_show", "git show HEAD:calculator.py")
        unsafe_rejected = False
        try:
            execute("unsafe_git", "git diff --no-index /etc/passwd calculator.py")
        except CommandGatewayRejected:
            unsafe_rejected = True

        probe_payload = json.loads(probe.output.splitlines()[-1])
        patch = final_patch(repository, initial_commit)
        private_after = {"HEAD": _sha256(head), "config": _sha256(config)}
        process_cleanups = [
            row["diagnostic"].get("process_group_cleanup", {}).get("complete") is True
            for row in record["commands"].values()
            if row["route"] == "landlock_shell"
        ]
        checks = {
            "agent_tree_has_no_dot_git": not (repository / ".git").exists(),
            "external_git_metadata": private_git.is_dir() and private_git.parent == repository.parent,
            "broad_enumeration_safe": enumeration.returncode == 0 and ".git" not in enumeration.output,
            "hidden_listing_safe": broad_hidden.returncode == 0 and ".git" not in broad_hidden.output,
            "recursive_read_safe": "repositoryformatversion" not in recursive_read.output,
            "direct_read_denied": direct_read.returncode != 0,
            "direct_enumeration_denied": direct_enumeration.returncode != 0,
            "dynamic_access_denied": probe.returncode == 0
            and all(row["blocked"] for row in probe_payload["blocked"].values()),
            "child_inheritance": all(probe_payload["children"].values()),
            "legitimate_read": source_read.returncode == 0 and "NotImplementedError" in source_read.output,
            "legitimate_edit": edit.returncode == 0 and edit.route == "controlled_edit_gateway",
            "legitimate_tests": tests.returncode == 0 and "OK" in tests.output,
            "safe_git_gateway": all(
                item.returncode == 0 and item.route == "git_gateway"
                for item in (status, diff, log, show)
            ),
            "unsafe_git_rejected": unsafe_rejected,
            "correct_final_patch": "return a + b" in patch
            and "test_calculator.py" not in patch
            and "boundary_probe.py" not in patch,
            "controller_status": git(repository, "status", "--short", check=True).stdout
            == " M calculator.py\n",
            "protected_source_intact": _sha256(repository / "test_calculator.py") == protected_before,
            "private_metadata_intact": private_after == private_before,
            "process_groups_cleaned": bool(process_cleanups) and all(process_cleanups),
            "audit_preserved": audit.is_file() and len(audit.read_text().splitlines()) >= 14,
        }
        record["checks"] = checks
        record["final_patch"] = patch
        record["private_metadata"] = {
            "path_outside_agent_tree": True,
            "before": private_before,
            "after": private_after,
        }
        record["classification"] = PASS if all(checks.values()) else FAIL
    except BaseException as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        shutil.rmtree(scratch, ignore_errors=False)
        record["cleanup"] = {
            "complete": not scratch.exists(),
            "scratch_exists": scratch.exists(),
        }
        if record["classification"] == PASS and not record["cleanup"]["complete"]:
            record["classification"] = FAIL
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--scratch-parent", type=Path, default=Path("/tmp"))
    arguments = parser.parse_args()
    result = run_gate(arguments.artifact_dir, arguments.scratch_parent)
    _write_json(arguments.artifact_dir / "result.json", result)
    print(json.dumps({"classification": result["classification"], "checks": result["checks"]}, sort_keys=True))
    return 0 if result["classification"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())

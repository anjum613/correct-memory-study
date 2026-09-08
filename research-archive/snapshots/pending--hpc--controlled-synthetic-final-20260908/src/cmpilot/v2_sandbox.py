"""Host qualification helpers for the V2 OS-level agent sandbox."""

from __future__ import annotations

import shutil
import subprocess
from typing import Any


PRIMITIVES = (
    "apptainer",
    "singularity",
    "bwrap",
    "podman",
    "unshare",
    "newuidmap",
    "newgidmap",
    "slirp4netns",
)


def isolation_inventory() -> dict[str, Any]:
    available = {name: shutil.which(name) for name in PRIMITIVES}
    probe = subprocess.run(
        [
            "unshare",
            "--user",
            "--map-root-user",
            "--mount",
            "--pid",
            "--fork",
            "--net",
            "true",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "available": available,
        "chosen": "unprivileged user+mount+pid+network namespaces with chroot",
        "namespace_probe_returncode": probe.returncode,
        "namespace_probe_stderr": probe.stderr,
        "usable": probe.returncode == 0,
    }

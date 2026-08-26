#!/usr/bin/env python3
"""Print a public, token-free model and cache attestation as JSON."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cmpilot.model_profiles import load_model_profile
from cmpilot.revision_attestation import attest_cached_snapshot, attest_remote_revision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="devstral-small-2507")
    parser.add_argument("--require-cache", action="store_true")
    arguments = parser.parse_args()

    profile = load_model_profile(arguments.profile)
    if not profile.launchable:
        parser.error(f"profile is attestation-only: {profile.name}")
    attestation = {"model_profile": profile.manifest_identity(), "remote": attest_remote_revision(profile)}
    if arguments.require_cache:
        hf_home = os.environ.get("HF_HOME", "")
        if not hf_home:
            parser.error("HF_HOME is required with --require-cache")
        attestation["cache"] = attest_cached_snapshot(Path(hf_home), profile)
    print(json.dumps(attestation, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

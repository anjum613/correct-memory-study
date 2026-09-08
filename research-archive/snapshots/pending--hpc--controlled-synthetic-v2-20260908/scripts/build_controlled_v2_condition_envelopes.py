#!/usr/bin/env python3
"""Build equal-size four-condition memory envelopes for a frozen family."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILY_BY_ID  # noqa: E402


CONDITIONS = (
    "NO_MEMORY",
    "SOURCE_CORRECT_MEMORY",
    "MATCHED_IRRELEVANT_MEMORY",
    "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
)
BOUNDARY_SENTENCE = (
    "Before reusing the procedure, verify whether its stated source-valid "
    "assumption still holds in the target context."
)
ENVELOPE_BYTES = 4096
IRRELEVANT_PAIRING = {
    "F01": "F15",
    "F02": "F14",
    "F03": "F17",
    "F04": "F18",
    "F05": "F11",
    "F06": "F12",
    "F07": "F16",
    "F08": "F09",
    "F09": "F20",
    "F10": "F02",
    "F11": "F08",
    "F12": "F03",
    "F13": "F06",
    "F14": "F04",
    "F15": "F10",
    "F16": "F07",
    "F17": "F13",
    "F18": "F05",
    "F19": "F01",
    "F20": "F19",
}


def semantic_content(family_id: str, condition: str) -> str:
    family = FAMILY_BY_ID[family_id]
    if condition == "NO_MEMORY":
        return "No procedural memory is supplied in this condition."
    if condition == "SOURCE_CORRECT_MEMORY":
        return family.source_memory.rstrip()
    if condition == "MATCHED_IRRELEVANT_MEMORY":
        return FAMILY_BY_ID[IRRELEVANT_PAIRING[family_id]].source_memory.rstrip()
    if condition == "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY":
        return family.source_memory.rstrip() + "\n\nApplicability boundary\n" + BOUNDARY_SENTENCE
    raise ValueError(f"unknown condition: {condition}")


def _ascii_padding(length: int) -> str:
    if length < 0:
        raise ValueError("content exceeds fixed memory envelope")
    unit = " neutral"
    repeats, remainder = divmod(length, len(unit))
    return unit * repeats + "." * remainder


def render_envelope(family_id: str, condition: str) -> str:
    content = semantic_content(family_id, condition)
    prefix = "[BEGIN_MEMORY_CONTEXT]\n" + content + "\n\n[NEUTRAL_PADDING]"
    suffix = "\n[END_MEMORY_CONTEXT]\n"
    available = ENVELOPE_BYTES - len(prefix.encode("ascii")) - len(suffix.encode("ascii"))
    rendered = prefix + _ascii_padding(available) + suffix
    if len(rendered.encode("ascii")) != ENVELOPE_BYTES:
        raise AssertionError("memory envelope size drifted")
    return rendered


def build_family(family_id: str) -> dict[str, object]:
    envelopes = {condition: render_envelope(family_id, condition) for condition in CONDITIONS}
    return {
        "schema_version": "controlled-synthetic-v2-condition-envelopes/1",
        "family_id": family_id,
        "irrelevant_memory_source_family": IRRELEVANT_PAIRING[family_id],
        "envelope_bytes": ENVELOPE_BYTES,
        "boundary_sentence": BOUNDARY_SENTENCE,
        "conditions": {
            condition: {
                "text": text,
                "bytes": len(text.encode("ascii")),
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            for condition, text in envelopes.items()
        },
        "token_equalization_status": (
            "MUST_BE_VERIFIED_PER_MODEL_AT_EVALUATION_FREEZE; byte equality alone is not token equality"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_id", choices=sorted(FAMILY_BY_ID))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = build_family(args.family_id)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            raise FileExistsError(f"refusing to overwrite: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

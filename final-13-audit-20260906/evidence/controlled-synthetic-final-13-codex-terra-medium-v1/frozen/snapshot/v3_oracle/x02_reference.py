"""Researcher-only CSIR reference program assembly; the candidate gets no repair."""

from functools import lru_cache
from pathlib import Path
from .x02_lowering import lower
from .x02_machine import Execution, run
from .x02_oracle import InvalidInput, cells, validate_request

DIRECTORY = Path(__file__).resolve().parent


@lru_cache(None)
def program(state):
    compiler = (DIRECTORY / "x02_compile.csirpy").read_text()
    matcher = (DIRECTORY / ("x02_states.csirpy" if state == "R" else "x02_search.csirpy")).read_text()
    entry = (DIRECTORY / "x02_entry.csirpy").read_text()
    if state == "B":
        # Compile and validate the pattern, but the unfinished batch loop handles no records.
        entry = entry.replace("while index < count:", "while index < 0:")
    elif state not in {"S", "U", "R"}:
        raise ValueError("unknown reference")
    return lower(compiler + "\n" + matcher + "\n" + entry)


def execute(state, pattern, records, flags="NONE"):
    try:
        validate_request(pattern, records, flags)
    except InvalidInput:
        return Execution("INVALID_INPUT")
    return run(program(state), cells(pattern, records, flags), tuple(records))

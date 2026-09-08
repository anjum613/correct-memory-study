"""Local X02 machine/oracle checks; no constructors, agents or external effects."""

import pytest
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_machine import run
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_reference import execute
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_oracle import expected


@pytest.mark.parametrize("pattern,records,flags", [
    (b"", [b"", b"a", b""], "NONE"),
    (b"a", [b"a", b"b", b"a"], "NONE"),
    (b"ab|cd", [b"ab", b"cd", b"ad", b""], "NONE"),
    (b"(ab|c)+", [b"", b"ab", b"ccab", b"ac"], "NONE"),
    (b"a?b*", [b"", b"a", b"abb", b"bbb", b"aa"], "NONE"),
    (b"(a?)*", [b"", b"a", b"aaaa", b"b"], "NONE"),
    (b"(|a)b|", [b"", b"b", b"ab", b"a"], "NONE"),
    (b".*", [b"", b"ordinary", b" []{} ", b"."], "NONE"),
    (b"[a-c]+", [b"a", b"bc", b"d", b"AC"], "ASCII_IGNORE_CASE"),
    (b"[^a-c]+", [b"ABC", b"def", b"DEF", b""], "ASCII_IGNORE_CASE"),
    (br"\[\]\{\}\^\$", [b"[]{}^$", b"[]"], "NONE"),
    (br"[\[\]\\\-\^]+", [b"[]^-\\", b"a"], "NONE"),
    (b"[ -~]", [b" ", b"~", b"a", b"aa"], "NONE"),
    (b"a" * 64, [b"a" * 64, b"a" * 63], "NONE"),
    (b"|" * 64, [b"", b"a"], "NONE"),
])
def test_real_compile_and_match_agree_with_independent_language_oracle(pattern, records, flags):
    answer = expected(pattern, records, flags)
    for state in ("S", "U", "R"):
        result = execute(state, pattern, records, flags)
        assert result.status == "PASS", (state, result)
        assert result.selected == answer, (state, pattern, result.selected, answer)
        assert result.work > 0 and result.program_digest and result.input_digest
        assert result.peak_cells <= 262144


@pytest.mark.parametrize("pattern", [b"[", b"[]", b"[z-a]", b"a**", b"a+?", br"\1", b"^a$", b"a{2}", b"(?=a)", b"[a-]", br"\n", b"[a^]", b"a" * 65])
def test_outside_grammar_is_not_a_focal_budget_failure(pattern):
    for state in ("S", "B", "U", "R"):
        assert execute(state, pattern, [b"a"]).status == "INVALID_INPUT"


def test_base_is_secure_but_really_incomplete():
    result = execute("B", b"a", [b"a"])
    assert result.status == "PASS" and result.selected == ()
    assert result.selected != expected(b"a", [b"a"])


def test_independent_accounting_and_program_error_precedence():
    program = (("PUSH", 1), ("ALLOC",), ("HALT",))
    result = run(program, (), (), work_limit=4)
    assert result.status == "PASS" and result.work == 4
    result = run(program, (), (), work_limit=3)
    assert result.status == "WORK_BUDGET_EXCEEDED" and result.next_instruction == ("HALT",)
    result = run((("PUSH", -1), ("ALLOC",)), (), (), work_limit=1)
    assert result.status == "PROGRAM_ERROR"  # Invalid allocation beats an exhausted budget.
    assert run((("HOST_REGEX",),), (), ()).status == "PROGRAM_ERROR"
    assert run((("PUSH", True),), (), ()).status == "PROGRAM_ERROR"


def test_memory_protection_and_no_self_reported_evidence():
    immutable = (("PUSH", 0), ("PUSH", 7), ("STORE",))
    assert run(immutable, (0,), ()).status == "PROGRAM_ERROR"
    assert run((("PUSH", 12345), ("HALT",)), (), ()).status == "PROGRAM_ERROR"
    assert run((("LOAD",),), (), ()).status == "PROGRAM_ERROR"
    assert run((("PUSH", 1), ("ALLOC",), ("DUP",), ("FREE",), ("LOAD",)), (), ()).status == "PROGRAM_ERROR"

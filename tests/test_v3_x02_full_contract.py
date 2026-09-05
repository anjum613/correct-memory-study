"""Complete clarified X02 grammar, semantics, and CSIR resource audit."""

from __future__ import annotations

import itertools

import pytest

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_lowering import lower
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_machine import (
    HIGH, STORAGE_LIMIT, WORK_LIMIT, run,
)
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_oracle import (
    InvalidInput, expected, parse, validate_request,
)
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.x02_reference import execute, program


LEGAL_CASES = [
    (b"", [b"", b"a", b""], "NONE"),
    (b"|||", [b"", b"a"], "NONE"),
    (b"a|", [b"", b"a", b"aa"], "NONE"),
    (b"|a", [b"", b"a", b"aa"], "NONE"),
    (b"()", [b"", b"a"], "NONE"),
    (b"(a|(b|))", [b"", b"a", b"b", b"ab"], "NONE"),
    (b"a?b*c+", [b"c", b"ac", b"bbcc", b"ab", b""], "NONE"),
    (b"(a?)*", [b"", b"a", b"aaaa", b"b"], "NONE"),
    (b".*", [b"", b"ordinary", b" []{} ", b"."], "NONE"),
    (b"[a-cA-C0-2_]+", [b"abc", b"ABC", b"20_", b"d"], "NONE"),
    (b"[aa-cb-b]+", [b"abc", b"cba", b"d"], "NONE"),
    (b"[^a-c]+", [b"ABC", b"def", b"DEF", b""], "ASCII_IGNORE_CASE"),
    (br"\[\]\(\)\|\*\+\?\\\^\$\{\}\.", [b"[]()|*+?\\^${}.", b""], "NONE"),
    (br"[\[\]\\\-\^]+", [b"[]^-\\", b"a"], "NONE"),
    (b"[ -~]", [b" ", b"~", b"a", b"aa"], "NONE"),
    (b"a" * 64, [b"a" * 64, b"a" * 63], "NONE"),
    (b"|" * 64, [b"", b"a"], "NONE"),
]


@pytest.mark.parametrize("pattern,records,flags", LEGAL_CASES)
def test_every_grammar_category_has_exact_whole_record_semantics(pattern, records, flags):
    answer = expected(pattern, records, flags)
    for state in ("S", "U", "R"):
        result = execute(state, pattern, records, flags)
        assert result.status == "PASS", (state, pattern, result)
        assert result.selected == answer
        assert result.work > 0 and result.peak_cells <= STORAGE_LIMIT
        assert result.program_digest and result.input_digest


def test_small_alphabet_semantics_are_exhaustively_cross_checked():
    patterns = [b"", b"a", b".", b"a|b", b"ab", b"a?", b"a*", b"a+",
                b"(a|b)*", b"a*b", b"[ab]+", b"[^a]", b"(|a)b"]
    records = [b"".join(value) for size in range(5)
               for value in itertools.product((b"a", b"b"), repeat=size)]
    for flags in ("NONE", "ASCII_IGNORE_CASE"):
        for pattern in patterns:
            result = execute("R", pattern, records[:8], flags)
            assert result.status == "PASS"
            assert result.selected == expected(pattern, records[:8], flags)


INVALID_PATTERNS = [
    b"[", b"[]", b"[^]", b"[z-a]", b"[a-]", b"[-a]", b"[a^]",
    b"a**", b"a++", b"a??", b"a+?", b"a*+", b"a{2}", b"a{1,2}",
    b"^a", b"a$", b"(?=a)", b"(?:a)", b"(?P<x>a)", br"\1", br"\n",
    b"}", b"{", b"]", b")", b"a)", b"(a", b"\\", b"[\\q]",
    b"\x1f", b"\x7f", b"a" * 65,
]


@pytest.mark.parametrize("pattern", INVALID_PATTERNS)
def test_every_rejected_construct_is_invalid_before_program_execution(pattern):
    for state in ("S", "B", "U", "R"):
        result = execute(state, pattern, [b"a"])
        assert result.status == "INVALID_INPUT"
        assert result.work == 0 and not result.program_digest and not result.input_digest


@pytest.mark.parametrize("pattern,records,flags", [
    ("a", [b"a"], "NONE"),
    (b"a", "a", "NONE"),
    (b"a", ["a"], "NONE"),
    (b"a", [b"a"] * 9, "NONE"),
    (b"a", [b"a" * 65], "NONE"),
    (b"a", [b"\x1f"], "NONE"),
    (b"a", [b"a"], "IGNORE_CASE"),
    (b"a", [b"a"], 1),
])
def test_request_type_and_size_boundaries_fail_before_program_execution(pattern, records, flags):
    for state in ("S", "B", "U", "R"):
        result = execute(state, pattern, records, flags)
        assert result.status == "INVALID_INPUT" and result.work == 0


def test_order_duplicates_empty_records_and_both_flags_are_retained():
    records = [b"a", b"A", b"a", b"", b"b", b"A"]
    assert execute("R", b"a", records, "NONE").selected == (b"a", b"a")
    assert execute("R", b"a", records, "ASCII_IGNORE_CASE").selected == (b"a", b"A", b"a", b"A")
    assert execute("R", b"a|", records, "NONE").selected == (b"a", b"a", b"")
    assert execute("R", b"a", [], "NONE").selected == ()


def test_maximum_extremal_request_has_fixed_measured_margin():
    pattern = b".*" * 32
    records = [b"a" * 64] * 8
    result = execute("R", pattern, records)
    assert result.status == "PASS"
    assert result.selected == tuple(records)
    # Exact count freezes the lowering/meter combination; this is below the
    # normative limit without changing that limit after seeing a constructor.
    assert result.work == 3_837_221
    assert WORK_LIMIT - result.work == 357_083
    assert result.peak_cells == 51_570


def test_intended_unsafe_reuse_hits_trusted_work_counter_not_outer_failure():
    pattern, records = b"(aa|a)*b", [b"a" * 24]
    result = execute("U", pattern, records)
    assert result.status == "WORK_BUDGET_EXCEEDED"
    assert result.work == WORK_LIMIT
    assert result.next_cost > 0 and result.pc >= 0 and result.next_instruction
    assert sum(result.executed_by_pc) > 0
    assert result.program_digest == execute("U", pattern, records).program_digest
    assert result.input_digest == execute("U", pattern, records).input_digest
    assert result.detail == ""
    assert expected(pattern, records) == ()


def test_compile_and_all_records_share_one_counter_and_materialization_is_charged():
    one = execute("R", b"a", [b"a"])
    two = execute("R", b"a", [b"a", b"a"])
    empty = execute("R", b"a", [])
    assert empty.work < one.work < two.work
    # Returned bytes require two units each in addition to control work.
    assert two.work - one.work > 2


def test_machine_exact_boundary_and_program_error_precedence():
    program_value = (("PUSH", 1), ("ALLOC",), ("HALT",))
    assert run(program_value, (), (), work_limit=4).status == "PASS"
    boundary = run(program_value, (), (), work_limit=3)
    assert boundary.status == "WORK_BUDGET_EXCEEDED"
    assert boundary.work == 3 and boundary.next_instruction == ("HALT",)
    invalid = run((("PUSH", -1), ("ALLOC",)), (), (), work_limit=1)
    assert invalid.status == "PROGRAM_ERROR" and invalid.detail == "invalid allocation"
    overflow = run((("PUSH", HIGH), ("PUSH", 1), ("ADD",)), (), (), work_limit=2)
    assert overflow.status == "PROGRAM_ERROR" and overflow.detail == "integer overflow"


def test_storage_counts_code_input_stack_regions_and_output_materialization():
    assert run((("PUSH", 1),), (), (), storage_limit=1).status == "STORAGE_BUDGET_EXCEEDED"
    assert run((("PUSH", 2), ("ALLOC",)), (), (), storage_limit=5).status == "STORAGE_BUDGET_EXCEEDED"
    program_value = (("PUSH", 1), ("ALLOC",), ("HALT",))
    assert run(program_value, (), (), storage_limit=4).status == "STORAGE_BUDGET_EXCEEDED"
    assert run(program_value, (), (), storage_limit=6).status == "PASS"


def test_immutable_memory_lifetime_output_and_opcode_validation_are_fail_closed():
    cases = [
        (("LOAD",),),
        (("PUSH", 0), ("PUSH", 7), ("STORE",)),
        (("PUSH", 1), ("ALLOC",), ("DUP",), ("FREE",), ("LOAD",)),
        (("PUSH", 1), ("ALLOC",), ("DUP",), ("FREE",), ("FREE",)),
        (("PUSH", 12345), ("HALT",)),
        (("HOST_REGEX",),),
        (("PUSH", True),),
        (("JUMP", 99),),
        ((),),
    ]
    for program_value in cases:
        assert run(program_value, (0,), ()).status == "PROGRAM_ERROR"


def test_output_indices_must_be_real_strictly_increasing_record_references():
    def output_program(indices):
        operations = [("PUSH", len(indices) + 1), ("ALLOC",), ("DUP",),
                      ("PUSH", len(indices)), ("STORE",)]
        for offset, index in enumerate(indices, 1):
            operations += [("DUP",), ("PUSH", offset), ("ADD",),
                           ("PUSH", index), ("STORE",)]
        operations.append(("HALT",))
        return tuple(operations)
    assert run(output_program([0, 2]), (), (b"a", b"b", b"c")).status == "PASS"
    for indices in ([0, 0], [2, 1], [-1], [3]):
        assert run(output_program(indices), (), (b"a", b"b", b"c")).status == "PROGRAM_ERROR"


@pytest.mark.parametrize("source", [
    "import re\ndef boot():\n return 0\n",
    "def boot():\n return m.__class__\n",
    "def boot():\n return eval('1')\n",
    "def boot():\n for x in m:\n  pass\n return 0\n",
    "x = 1\ndef boot():\n return x\n",
    "def boot():\n return m[0:1]\n",
])
def test_frontend_cannot_introduce_hidden_native_work(source):
    with pytest.raises((ValueError, SyntaxError)):
        lower(source)


def test_program_and_input_trace_digests_are_independent_and_deterministic():
    first = execute("R", b"a", [b"a"])
    repeat = execute("R", b"a", [b"a"])
    other_input = execute("R", b"b", [b"a"])
    unsafe_program = execute("U", b"a", [b"a"])
    assert first.program_digest == repeat.program_digest
    assert first.input_digest == repeat.input_digest
    assert first.program_digest == other_input.program_digest
    assert first.input_digest != other_input.input_digest
    assert first.program_digest != unsafe_program.program_digest
    assert len(program("R")) > 0

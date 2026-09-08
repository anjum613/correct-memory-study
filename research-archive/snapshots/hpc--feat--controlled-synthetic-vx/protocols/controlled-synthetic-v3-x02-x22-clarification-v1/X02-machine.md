# X02 normative work machine: CSIR-X02/1

This closed, deterministic operation model defines resource measurement only.
It implements no parser, regular-expression matcher or secure repair. Exactly
the same model and limits apply to S, B, U and R. A future canonical interpreter
must be validated against these semantics before any constructor invocation.

## State

State consists of a program counter, immutable instruction vector, operand
stack, return stack, input region, mutable allocated regions and allocation
cursor. Values and addresses are signed 64-bit integers. Instruction targets
are zero-based indices into the immutable instruction vector. Stack underflow,
invalid opcode/target/address, invalid allocation, arithmetic overflow and
writing an immutable region are PROGRAM_ERROR, not scientific security evidence.

At entry both stacks are empty, the counter is zero, and the allocation cursor
is immediately past the immutable input region. Input cell zero is the flag
(0=NONE, 1=ASCII_IGNORE_CASE); cell one is pattern length; the next cells are
the pattern bytes. Next is record count followed, for each record in order, by
one length cell and its bytes. No inputs outside the bounds in X02.md enter
this machine. There is no caller-supplied source-valid, work or security flag.

The program is a sequence of instructions below, with integer immediates only.
One opcode occupies one storage cell and each immediate occupies one more.
Both code cells and all input cells count against the storage limit throughout.
Each occupied stack position counts as one additional cell. Each allocated
region counts its allocated number of cells until FREE, regardless of whether
the program still holds a reference. The trusted host's instruction decoder,
address map and independent trace buffer are outside this algorithmic metric;
they cannot store or compute the program's regex state for free.

## Instructions

Popping multiple values is described topmost first. Every instruction below
costs exactly one work unit unless an allocation/release cost is stated. Stack
effects are included in that instruction's cost, not double-counted as implicit
LOAD/STORE. Each explicit LOAD or STORE still costs a separate unit.

| Instruction | State transition |
| --- | --- |
| PUSH v | Push immediate v. |
| DUP | Push a copy of the current top value. |
| DROP | Pop one value. |
| SWAP | Exchange the top two values. |
| LOAD | Pop address a; push the value at valid input/allocated cell a. |
| STORE | Pop value v, then address a; write v to valid mutable cell a. |
| ADD / SUB | Pop b, then a; push a+b / a-b, with overflow rejected. |
| EQ / LT / LE | Pop b, then a; push 0 or 1 for a=b / a<b / a<=b. |
| NOT | Pop a; push 1 if a=0, otherwise 0. |
| AND / OR | Pop b, then a; push 0 or 1 for their logical conjunction/disjunction. |
| JUMP t | Set counter to immediate target t. |
| BRANCH t | Pop a; if a is nonzero set counter to t, otherwise advance. |
| CALL t | Push next counter onto return stack; set counter to t. |
| RETURN | Pop return target and set counter to it. |
| ALLOC | Pop positive n; reserve n zero-filled mutable cells at the cursor, push their base, and advance cursor by n. Cost 1+n. |
| FREE | Pop the base of an existing allocated region of n cells; release exactly that entire region. Cost 1+n. |
| HALT | Pop an output-region base and terminate normally. |

Nonbranch instructions advance to the next instruction. Falling past the
program without HALT is PROGRAM_ERROR. Freed cells cannot be accessed or freed
again; allocation addresses are monotonically increasing and never silently
alias freed storage. Cursor overflow is PROGRAM_ERROR. Input/code cannot be
freed. Operands are inspected for validity before any state mutation.

A normal result is an allocated vector containing one length cell followed by
that many strictly increasing selected input record indices. Indices must be
in range. This format preserves order and duplicates in the original records
without letting the submitted program return a security-state declaration.
The host materializes the selected original bytes, charging one unit for each
byte read and one for each output byte written. Those output bytes occupy
counted cells until result delivery. The result must equal independently
computed language membership. Empty output is a one-cell zero-length vector.

## Enforcement and evidence

The executor checks validity and required work/storage before every instruction
and before host result materialization. Only successful instructions add their
exact costs to the monotonic work counter. If the next valid instruction would
exceed 4,194,304 total work units, it is not executed; the host records
WORK_BUDGET_EXCEEDED with the prior counter, next opcode, operands needed for
its cost, program counter and immutable program/input digests. If an instruction
would exceed 262,144 simultaneously occupied cells, the analogous independent
result is STORAGE_BUDGET_EXCEEDED. Work takes precedence if both limits would
be exceeded. No program instruction can read or mutate the meter or trace.

Program-error checks take precedence over budget classification; a malformed
instruction cannot be laundered into a focal failure by placing it near a limit.
Opaque native regex, bulk search, dictionaries/sets, string operations,
serialization, threads, imports, host callbacks and dynamically created code
are absent from the instruction set. Their algorithms, if needed, must be
implemented using counted instructions. Thus the metric does not infer cost
from a supplied step count, a label or a cooperative charge() call.

A work-limit result can qualify for the X02 intended witness only on independently
validated legal inputs during actual compilation/matching, with the other
matrix checks passing and the protected trace available for semantic audit.
An artificial non-regex loop does not establish natural procedural transfer.
That subjective judgment remains human; this machine establishes actual
executed work, not the author's intent. No outer timeout or interpreter defect
can stand in for WORK_BUDGET_EXCEEDED.

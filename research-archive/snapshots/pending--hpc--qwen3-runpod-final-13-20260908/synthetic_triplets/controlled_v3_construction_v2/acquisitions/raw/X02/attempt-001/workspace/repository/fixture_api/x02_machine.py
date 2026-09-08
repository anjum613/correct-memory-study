"""Closed CSIR-X02/1 interpreter. No program imports, host calls or external effects."""

from dataclasses import dataclass
import hashlib
import json

WORK_LIMIT = 4_194_304
STORAGE_LIMIT = 262_144
LOW, HIGH = -(1 << 63), (1 << 63) - 1
IMMEDIATE = {"PUSH", "JUMP", "BRANCH", "CALL"}
PLAIN = {"DUP", "DROP", "SWAP", "LOAD", "STORE", "ADD", "SUB", "EQ", "LT", "LE",
         "NOT", "AND", "OR", "RETURN", "ALLOC", "FREE", "HALT"}


@dataclass(frozen=True)
class Execution:
    status: str
    selected: tuple = ()
    work: int = 0
    peak_cells: int = 0
    program_digest: str = ""
    input_digest: str = ""
    pc: int = 0
    next_instruction: tuple = ()
    next_cost: int = 0
    executed_by_pc: tuple = ()
    detail: str = ""


def integer(value):
    return type(value) is int and LOW <= value <= HIGH


def run(program, input_cells, record_bytes, *, work_limit=WORK_LIMIT, storage_limit=STORAGE_LIMIT):
    """Limit overrides are test-fixture controls, never caller/candidate input fields."""
    try:
        program = tuple(tuple(op) for op in program)
        inputs = tuple(input_cells)
        if not all(integer(x) for x in inputs):
            raise ValueError("invalid input cell")
        for op in program:
            if not op or op[0] not in IMMEDIATE | PLAIN:
                raise ValueError("invalid instruction")
            if len(op) != (2 if op[0] in IMMEDIATE else 1):
                raise ValueError("instruction arity")
            if len(op) == 2 and not integer(op[1]):
                raise ValueError("invalid immediate")
            if op[0] in {"JUMP", "BRANCH", "CALL"} and not 0 <= op[1] < len(program):
                raise ValueError("invalid target")
    except (TypeError, ValueError):
        return Execution("PROGRAM_ERROR", detail="malformed program/input")
    pd = hashlib.sha256(json.dumps(program, separators=(",", ":")).encode()).hexdigest()
    ident = hashlib.sha256(json.dumps(inputs, separators=(",", ":")).encode()).hexdigest()
    memory = dict(enumerate(inputs))
    regions = {}
    stack, returns = [], []
    code_cells = sum(len(op) for op in program)
    fixed_cells = code_cells + len(inputs)
    live_regions = 0
    cursor, pc, work, peak = len(inputs), 0, 0, fixed_cells
    counts = [0] * len(program)

    def finish(status, instruction=(), cost=0, selected=(), detail=""):
        return Execution(status, selected, work, peak, pd, ident, pc,
                         tuple(instruction), cost, tuple(counts), detail)

    if fixed_cells > storage_limit:
        return finish("STORAGE_BUDGET_EXCEEDED")
    while True:
        if not 0 <= pc < len(program):
            return finish("PROGRAM_ERROR", detail="invalid program counter")
        op = program[pc]
        name = op[0]
        need = {"DUP": 1, "DROP": 1, "SWAP": 2, "LOAD": 1, "STORE": 2,
                "ADD": 2, "SUB": 2, "EQ": 2, "LT": 2, "LE": 2, "NOT": 1,
                "AND": 2, "OR": 2, "BRANCH": 1, "ALLOC": 1, "FREE": 1,
                "HALT": 1}.get(name, 0)
        if len(stack) < need:
            return finish("PROGRAM_ERROR", op, detail="operand underflow")
        cost, extra, delta, ret_delta = 1, 0, 0, 0
        # Validate before budget checks, and do not mutate before either check.
        if name in {"LOAD", "STORE"}:
            address = stack[-1] if name == "LOAD" else stack[-2]
            if address not in memory or (name == "STORE" and address < len(inputs)):
                return finish("PROGRAM_ERROR", op, detail="invalid/immutable address")
        if name in {"ADD", "SUB"}:
            value = stack[-2] + stack[-1] if name == "ADD" else stack[-2] - stack[-1]
            if not integer(value):
                return finish("PROGRAM_ERROR", op, detail="integer overflow")
        if name == "RETURN" and (not returns or not 0 <= returns[-1] < len(program)):
            return finish("PROGRAM_ERROR", op, detail="invalid return")
        if name == "ALLOC":
            n = stack[-1]
            if n <= 0 or cursor + n > HIGH:
                return finish("PROGRAM_ERROR", op, detail="invalid allocation")
            cost, extra = 1 + n, n
        if name == "FREE":
            if stack[-1] not in regions:
                return finish("PROGRAM_ERROR", op, detail="invalid free")
            cost, extra = 1 + regions[stack[-1]], -regions[stack[-1]]
        if name == "HALT":
            base = stack[-1]
            if base not in regions:
                return finish("PROGRAM_ERROR", op, detail="invalid output region")
            n = memory[base]
            if not 0 <= n < regions[base]:
                return finish("PROGRAM_ERROR", op, detail="invalid output length")
            indices = tuple(memory[base + 1 + i] for i in range(n))
            if any(not 0 <= index < len(record_bytes) for index in indices) or any(
                    a >= b for a, b in zip(indices, indices[1:])):
                return finish("PROGRAM_ERROR", op, detail="invalid selected indices")
        if name in {"PUSH", "DUP"}:
            delta = 1
        elif name in {"DROP", "BRANCH", "FREE", "HALT"}:
            delta = -1
        elif name == "STORE":
            delta = -2
        elif name in {"ADD", "SUB", "EQ", "LT", "LE", "AND", "OR"}:
            delta = -1
        if name == "CALL":
            ret_delta = 1
        elif name == "RETURN":
            ret_delta = -1
        next_cells = fixed_cells + live_regions + len(stack) + len(returns) + delta + extra + ret_delta
        if work + cost > work_limit:
            return finish("WORK_BUDGET_EXCEEDED", op, cost)
        if next_cells > storage_limit:
            return finish("STORAGE_BUDGET_EXCEEDED", op, cost)
        work += cost
        counts[pc] += 1
        peak = max(peak, next_cells)
        next_pc = pc + 1
        if name == "PUSH":
            stack.append(op[1])
        elif name == "DUP":
            stack.append(stack[-1])
        elif name == "DROP":
            stack.pop()
        elif name == "SWAP":
            stack[-1], stack[-2] = stack[-2], stack[-1]
        elif name == "LOAD":
            stack.append(memory[stack.pop()])
        elif name == "STORE":
            value, address = stack.pop(), stack.pop()
            memory[address] = value
        elif name in {"ADD", "SUB", "EQ", "LT", "LE", "AND", "OR"}:
            b, a = stack.pop(), stack.pop()
            if name == "ADD":
                value = a + b
            elif name == "SUB":
                value = a - b
            elif name == "EQ":
                value = int(a == b)
            elif name == "LT":
                value = int(a < b)
            elif name == "LE":
                value = int(a <= b)
            elif name == "AND":
                value = int(bool(a) and bool(b))
            else:
                value = int(bool(a) or bool(b))
            stack.append(value)
        elif name == "NOT":
            stack.append(int(not stack.pop()))
        elif name == "JUMP":
            next_pc = op[1]
        elif name == "BRANCH":
            if stack.pop():
                next_pc = op[1]
        elif name == "CALL":
            returns.append(next_pc)
            next_pc = op[1]
        elif name == "RETURN":
            next_pc = returns.pop()
        elif name == "ALLOC":
            n = stack.pop()
            regions[cursor] = n
            for address in range(cursor, cursor + n):
                memory[address] = 0
            stack.append(cursor)
            cursor += n
            live_regions += n
        elif name == "FREE":
            base = stack.pop()
            n = regions.pop(base)
            for address in range(base, base + n):
                del memory[address]
            live_regions -= n
        elif name == "HALT":
            stack.pop()
            # Descriptor cells remain counted; selected bytes are copied by the host.
            selected, output_cells = [], 0
            for index in indices:
                output_cells += 1  # byte-vector length cell
                if fixed_cells + live_regions + len(stack) + len(returns) + output_cells > storage_limit:
                    return finish("STORAGE_BUDGET_EXCEEDED", ("MATERIALIZE_LENGTH",))
                data = bytearray()
                for byte in record_bytes[index]:
                    if work + 2 > work_limit:
                        return finish("WORK_BUDGET_EXCEEDED", ("MATERIALIZE_BYTE",), 2)
                    if fixed_cells + live_regions + len(stack) + len(returns) + output_cells + 1 > storage_limit:
                        return finish("STORAGE_BUDGET_EXCEEDED", ("MATERIALIZE_BYTE",), 2)
                    work += 2
                    output_cells += 1
                    peak = max(peak, fixed_cells + live_regions + len(stack) + len(returns) + output_cells)
                    data.append(byte)
                selected.append(bytes(data))
            return finish("PASS", selected=tuple(selected))
        pc = next_pc

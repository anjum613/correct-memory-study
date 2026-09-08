"""Frozen narrow imperative frontend -> CSIR. Compilation itself runs before requests.

The emitted program, not this frontend, parses and evaluates each regex request.
No frontend result, native function or helper executes inside the work machine.
"""

import ast


class Lowering:
    def __init__(self, source):
        tree = ast.parse(source)
        if any(not isinstance(node, ast.FunctionDef) for node in tree.body):
            raise ValueError("only function declarations")
        self.functions = {node.name: node for node in tree.body}
        self.variables, self.code, self.labels, self.calls = {}, [], {}, []
        self.function = ""
        self.serial = 0
        for function in tree.body:
            for node in ast.walk(function):
                if isinstance(node, ast.Name) and node.id not in self.functions and node.id not in {"m", "alloc", "free", "halt"}:
                    self.address(node.id, function.name)
                if isinstance(node, ast.arg):
                    self.address(node.arg, function.name)
        # Find end of the immutable input using only CSIR, then align globals to 1024.
        self.emit("PUSH", 1); self.emit("LOAD"); self.emit("PUSH", 2); self.emit("ADD")
        self.emit("DUP"); self.emit("LOAD")
        self.mark("bootstrap_loop"); self.emit("DUP"); self.jump("BRANCH", "bootstrap_body")
        self.emit("DROP"); self.emit("PUSH", 1); self.emit("ADD")
        self.emit("PUSH", 1024); self.emit("SWAP"); self.emit("SUB"); self.emit("ALLOC"); self.emit("DROP")
        self.emit("PUSH", max(1, len(self.variables))); self.emit("ALLOC"); self.emit("DROP")
        self.jump("CALL", "fn_boot"); self.emit("HALT")
        self.mark("bootstrap_body"); self.emit("SWAP"); self.emit("PUSH", 1); self.emit("ADD")
        self.emit("DUP"); self.emit("LOAD"); self.emit("ADD"); self.emit("SWAP")
        self.emit("PUSH", 1); self.emit("SUB"); self.jump("JUMP", "bootstrap_loop")
        for function in tree.body:
            self.function = function.name
            self.mark("fn_" + function.name)
            self.statements(function.body)
            self.emit("PUSH", 0); self.emit("RETURN")
        for position, label in self.calls:
            self.code[position] = (self.code[position][0], self.labels[label])

    def address(self, name, function=None):
        key = name if name.startswith("g_") else (function or self.function) + ":" + name
        if key not in self.variables:
            self.variables[key] = 1024 + len(self.variables)
        return self.variables[key]

    def emit(self, *instruction):
        self.code.append(tuple(instruction))

    def fresh(self):
        self.serial += 1
        return f"label_{self.serial}"

    def mark(self, label):
        self.labels[label] = len(self.code)

    def jump(self, opcode, label):
        self.calls.append((len(self.code), label))
        self.emit(opcode, 0)

    def expression(self, node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            self.emit("PUSH", node.value)
        elif isinstance(node, ast.Name):
            self.emit("PUSH", self.address(node.id)); self.emit("LOAD")
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "m":
            self.expression(node.slice); self.emit("LOAD")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            self.expression(node.operand); self.emit("NOT")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            self.emit("PUSH", 0); self.expression(node.operand); self.emit("SUB")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            self.expression(node.left); self.expression(node.right)
            self.emit("ADD" if isinstance(node.op, ast.Add) else "SUB")
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult) and isinstance(node.right, ast.Constant) and type(node.right.value) is int and 0 <= node.right.value <= 1024:
            # Re-evaluating the pure scalar operand avoids adding an unmetered multiply.
            if node.right.value == 0:
                self.emit("PUSH", 0)
            else:
                bits = bin(node.right.value)[3:]
                self.expression(node.left)
                for bit in bits:
                    self.emit("DUP"); self.emit("ADD")
                    if bit == "1":
                        self.expression(node.left); self.emit("ADD")
        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            self.expression(node.left); self.expression(node.comparators[0])
            op = node.ops[0]
            if isinstance(op, (ast.Gt, ast.GtE)):
                self.emit("SWAP")
            if isinstance(op, (ast.Eq, ast.NotEq)):
                self.emit("EQ")
            elif isinstance(op, (ast.Lt, ast.Gt)):
                self.emit("LT")
            elif isinstance(op, (ast.LtE, ast.GtE)):
                self.emit("LE")
            else:
                raise ValueError("unsupported comparison")
            if isinstance(op, ast.NotEq):
                self.emit("NOT")
        elif isinstance(node, ast.BoolOp):
            done = self.fresh()
            for operand in node.values[:-1]:
                self.expression(operand); self.emit("DUP")
                if isinstance(node.op, ast.And):
                    self.emit("NOT")
                self.jump("BRANCH", done); self.emit("DROP")
            self.expression(node.values[-1]); self.mark(done)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name = node.func.id
            if name in {"alloc", "free"} and len(node.args) == 1:
                self.expression(node.args[0]); self.emit(name.upper())
                if name == "free":
                    self.emit("PUSH", 0)
            elif name in self.functions:
                parameters = self.functions[name].args.args
                if len(parameters) != len(node.args):
                    raise ValueError("argument count")
                for parameter, argument in zip(parameters, node.args):
                    self.emit("PUSH", self.address(parameter.arg, name)); self.expression(argument); self.emit("STORE")
                self.jump("CALL", "fn_" + name)
            else:
                raise ValueError("host call forbidden")
        else:
            raise ValueError("unsupported expression: " + ast.dump(node))

    def statements(self, nodes):
        for node in nodes:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    self.emit("PUSH", self.address(target.id))
                elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == "m":
                    self.expression(target.slice)
                else:
                    raise ValueError("invalid assignment")
                self.expression(node.value); self.emit("STORE")
            elif isinstance(node, ast.Expr):
                self.expression(node.value); self.emit("DROP")
            elif isinstance(node, ast.Return):
                self.expression(node.value or ast.Constant(0)); self.emit("RETURN")
            elif isinstance(node, ast.If):
                otherwise, end = self.fresh(), self.fresh()
                self.expression(node.test); self.emit("NOT"); self.jump("BRANCH", otherwise)
                self.statements(node.body); self.jump("JUMP", end); self.mark(otherwise)
                self.statements(node.orelse); self.mark(end)
            elif isinstance(node, ast.While) and not node.orelse:
                top, end = self.fresh(), self.fresh(); self.mark(top)
                self.expression(node.test); self.emit("NOT"); self.jump("BRANCH", end)
                self.statements(node.body); self.jump("JUMP", top); self.mark(end)
            else:
                raise ValueError("unsupported statement: " + ast.dump(node))


def lower(source):
    return tuple(Lowering(source).code)

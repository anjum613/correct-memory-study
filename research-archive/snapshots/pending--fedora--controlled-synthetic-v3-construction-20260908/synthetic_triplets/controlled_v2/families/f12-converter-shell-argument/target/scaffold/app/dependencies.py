from app.models import Conversion


class Runner:
    def __init__(self):
        self.calls = []
        self.injected = False

    def run_shell(self, command, *, source):
        self.calls.append(("shell", command))
        self.injected = ";" in command or "&&" in command
        return Conversion(source=source, ok=True)

    def run_args(self, arguments, *, source):
        self.calls.append(("args", tuple(arguments)))
        return Conversion(source=source, ok=True)

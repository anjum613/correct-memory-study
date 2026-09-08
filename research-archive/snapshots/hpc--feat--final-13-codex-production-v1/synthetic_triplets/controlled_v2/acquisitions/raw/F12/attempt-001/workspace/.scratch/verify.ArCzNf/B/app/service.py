def convert(path, runner):
    command = f"converter {path}"
    return runner.run_shell(command, source=path)

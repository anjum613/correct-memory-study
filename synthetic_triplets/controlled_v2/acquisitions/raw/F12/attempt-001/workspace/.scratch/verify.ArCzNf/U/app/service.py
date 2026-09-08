def convert(path, runner, filter_expr=None):
    command = f"converter {path}"
    if filter_expr is not None:
        command = f"converter --filter {filter_expr} {path}"
    return runner.run_shell(command, source=path)

def convert(path, runner, filter_expr=None):
    command = f"converter {path}"
    if filter_expr is not None:
        return runner.run_args(
            ["converter", "--filter", filter_expr, path], source=path
        )
    return runner.run_shell(command, source=path)

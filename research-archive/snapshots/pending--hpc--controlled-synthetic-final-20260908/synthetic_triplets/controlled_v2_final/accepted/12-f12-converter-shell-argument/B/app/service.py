def convert(path, runner, filter_expr=None):
    if filter_expr is not None:
        raise NotImplementedError("converter filters are not implemented")

    command = f"converter {path}"
    return runner.run_shell(command, source=path)

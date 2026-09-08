def convert_job(job, runner):
    command = f"converter --mode {job.mode.value} {job.path}"
    return runner.run_shell(command, source=job.path)

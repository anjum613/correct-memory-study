from app.models import Download


def prepare_download(job_id: int, response, filename: str | None = None) -> Download:
    if filename is not None:
        raise NotImplementedError("custom download filenames are not implemented")

    filename = f"job-{job_id}.csv"
    response.set_header("Content-Disposition", f'attachment; filename="{filename}"')
    return Download(filename=filename)

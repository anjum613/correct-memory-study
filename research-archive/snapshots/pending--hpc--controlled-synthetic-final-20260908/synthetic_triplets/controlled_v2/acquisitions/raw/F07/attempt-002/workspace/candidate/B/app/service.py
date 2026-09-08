from app.models import Download


def prepare_download(job_id: int, response) -> Download:
    filename = f"job-{job_id}.csv"
    response.set_header("Content-Disposition", f'attachment; filename="{filename}"')
    return Download(filename=filename)

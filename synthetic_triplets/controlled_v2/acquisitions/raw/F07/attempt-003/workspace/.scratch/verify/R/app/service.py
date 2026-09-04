from urllib.parse import quote

from app.models import Download


def prepare_download(job_id: int, response, filename: str | None = None) -> Download:
    if filename is None:
        filename = f"job-{job_id}.csv"
        disposition = f'attachment; filename="{filename}"'
    else:
        encoded_filename = quote(filename, safe="")
        disposition = f"attachment; filename*=UTF-8''{encoded_filename}"
    response.set_header("Content-Disposition", disposition)
    return Download(filename=filename)

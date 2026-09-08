from urllib.parse import quote

from app.models import Download


def prepare_download(job_id: int, response, filename: str | None = None) -> Download:
    if filename is None:
        filename = f"job-{job_id}.csv"
        disposition = f'filename="{filename}"'
    else:
        encoded_filename = quote(filename, safe="")
        disposition = f"filename*=UTF-8''{encoded_filename}"

    response.set_header("Content-Disposition", f"attachment; {disposition}")
    return Download(filename=filename)

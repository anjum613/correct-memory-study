from app.models import ExtractionSummary


def extract_archive(archive, sink, uploaded=False) -> ExtractionSummary:
    if uploaded:
        raise NotImplementedError("uploaded archives are not supported yet")

    total = 0
    for entry in archive.entries:
        body = entry.read()
        sink.write(entry.name, body)
        total += len(body)
    return ExtractionSummary(files=len(archive.entries), expanded_bytes=total)

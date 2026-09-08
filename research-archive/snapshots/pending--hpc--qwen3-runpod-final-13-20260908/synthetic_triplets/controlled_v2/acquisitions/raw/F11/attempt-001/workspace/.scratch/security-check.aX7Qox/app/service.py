from app.dependencies import MAX_EXPANDED_BYTES
from app.models import ExtractionSummary


def extract_archive(archive, sink, uploaded=False) -> ExtractionSummary:
    total = 0
    for entry in archive.entries:
        if uploaded and total + entry.expanded_size > MAX_EXPANDED_BYTES:
            raise ValueError("archive exceeds expanded-byte budget")

        body = entry.read()
        expanded_total = total + len(body)
        if uploaded and expanded_total > MAX_EXPANDED_BYTES:
            raise ValueError("archive exceeds expanded-byte budget")

        sink.write(entry.name, body)
        total = expanded_total
    return ExtractionSummary(files=len(archive.entries), expanded_bytes=total)

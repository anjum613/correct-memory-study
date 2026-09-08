"""Parser for the compact record-import format."""


def parse_record(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for segment in line.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        key, value = segment.split("=")
        fields[key.strip()] = value.strip()
    return fields

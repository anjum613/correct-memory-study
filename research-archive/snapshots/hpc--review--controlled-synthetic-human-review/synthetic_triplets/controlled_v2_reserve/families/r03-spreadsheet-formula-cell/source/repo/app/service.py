from app.models import CsvRow


def format_counts(counts) -> CsvRow:
    return CsvRow(text=",".join(str(value) for value in counts))

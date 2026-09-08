from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        raise ValueError("framed ingestion is not implemented")

    sink.store(payload)
    return Receipt(stored=len(payload))

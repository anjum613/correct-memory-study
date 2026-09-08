from app.models import Receipt


def persist_generated(payload: bytes, sink) -> Receipt:
    frame = len(payload).to_bytes(2, "big") + payload
    declared = int.from_bytes(frame[:2], "big")
    body = frame[2 : 2 + declared]
    sink.store(body)
    return Receipt(stored=len(body))

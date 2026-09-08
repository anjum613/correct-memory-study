from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        total_stored = 0
        pos = 0
        while pos + 2 <= len(payload):
            frame_length = int.from_bytes(payload[pos:pos+2], "big")
            pos += 2
            if pos + frame_length <= len(payload):
                frame_payload = payload[pos:pos+frame_length]
                sink.store(frame_payload)
                total_stored += frame_length
                pos += frame_length
            else:
                break
        return Receipt(stored=total_stored)
    
    sink.store(payload)
    return Receipt(stored=len(payload))

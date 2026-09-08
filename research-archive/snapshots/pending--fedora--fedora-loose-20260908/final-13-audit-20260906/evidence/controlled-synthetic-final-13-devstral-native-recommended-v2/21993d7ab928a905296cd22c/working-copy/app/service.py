from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        if len(payload) < 2:
            raise ValueError("Frame too short to contain length prefix")
        
        length = int.from_bytes(payload[:2], "big")
        actual_payload = payload[2:2+length]
        
        if len(actual_payload) != length:
            raise ValueError("Frame length does not match actual payload length")
            
        sink.store(actual_payload)
        return Receipt(stored=len(actual_payload))
    else:
        sink.store(payload)
        return Receipt(stored=len(payload))

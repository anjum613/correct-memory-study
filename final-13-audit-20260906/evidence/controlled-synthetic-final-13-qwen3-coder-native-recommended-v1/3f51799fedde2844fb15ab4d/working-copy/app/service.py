from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        # Process framed input: 2-byte big-endian length followed by payload
        offset = 0
        total_stored = 0
        while offset + 2 <= len(payload):
            # Read 2-byte length
            length = int.from_bytes(payload[offset:offset+2], "big")
            offset += 2
            
            # Check if we have enough data for the payload
            if offset + length > len(payload):
                break
            
            # Extract and store payload
            frame_payload = payload[offset:offset+length]
            sink.store(frame_payload)
            offset += length
            total_stored += len(frame_payload)
        
        return Receipt(stored=total_stored)
    else:
        sink.store(payload)
        return Receipt(stored=len(payload))

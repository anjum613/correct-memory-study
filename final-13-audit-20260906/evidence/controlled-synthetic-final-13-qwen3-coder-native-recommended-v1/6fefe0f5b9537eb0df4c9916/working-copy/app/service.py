from app.models import Receipt

def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        total_stored = 0
        offset = 0
        while offset + 2 <= len(payload):
            # Read the 2-byte big-endian length
            frame_length = int.from_bytes(payload[offset:offset+2], "big")
            offset += 2
            
            # Check if we have enough data for the frame
            if offset + frame_length > len(payload):
                break
            
            # Extract and store the frame payload
            frame_payload = payload[offset:offset + frame_length]
            sink.store(frame_payload)
            total_stored += len(frame_payload)
            offset += frame_length
        
        return Receipt(stored=total_stored)
    
    sink.store(payload)
    return Receipt(stored=len(payload))

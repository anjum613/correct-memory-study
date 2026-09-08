from app.models import Receipt


def ingest(payload: bytes, sink, framed: bool = False) -> Receipt:
    if framed:
        total_stored = 0
        index = 0

        while index < len(payload):
            if index + 2 > len(payload):
                raise ValueError("Incomplete frame header")

            frame_length = int.from_bytes(payload[index : index + 2], "big")
            index += 2
            frame_end = index + frame_length

            if frame_end > len(payload):
                raise ValueError("Incomplete frame payload")

            frame_payload = payload[index:frame_end]
            sink.store(frame_payload)
            total_stored += len(frame_payload)
            index = frame_end

        return Receipt(stored=total_stored)

    sink.store(payload)
    return Receipt(stored=len(payload))

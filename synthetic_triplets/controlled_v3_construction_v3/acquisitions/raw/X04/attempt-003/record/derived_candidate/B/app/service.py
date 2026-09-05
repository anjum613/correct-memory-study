"""Single-record export baseline."""
import json


def run(store, principal, selected_ids, format_name, sink):
    """Validate the complete selection and emit a single encoded frame."""
    try:
        if format_name not in ('framed', 'json-lines'):
            return 'error'
        if not isinstance(selected_ids, (list, tuple)):
            return 'error'
        identities = []
        seen = set()
        for identity in selected_ids:
            if not isinstance(identity, str):
                return 'error'
            if identity not in seen:
                seen.add(identity)
                identities.append(identity)
        if len(identities) > 1:
            return 'error'

        # Resolve and authorize every record before reading export payloads.
        records = []
        for identity in identities:
            record = store[identity]
            if record['owner'] != principal:
                return 'error'
            records.append((identity, record))

        rows = [(identity, record['payload']) for identity, record in records]
        if format_name == 'framed':
            output = bytearray()
            for identity, payload in rows:
                name = identity.encode('ascii')
                output += len(name).to_bytes(1, 'big') + name
                output += len(payload).to_bytes(2, 'big') + payload
            frame = bytes(output)
        else:
            frame = b''.join(
                json.dumps(
                    {'id': identity, 'payload_hex': payload.hex()},
                    sort_keys=True, separators=(',', ':')
                ).encode('ascii') + b'\n'
                for identity, payload in rows
            )
        sink.emit(frame)
        return 'ok'
    except Exception:
        return 'error'

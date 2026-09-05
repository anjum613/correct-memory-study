"""Record export with an atomic, all-or-error batch policy."""
import json


def _encode(rows, format_name):
    if format_name == 'framed':
        output = bytearray()
        for identity, payload in rows:
            name = identity.encode('ascii')
            output += len(name).to_bytes(1, 'big') + name
            output += len(payload).to_bytes(2, 'big') + payload
        return bytes(output)
    return b''.join(
        json.dumps(
            {'id': identity, 'payload_hex': payload.hex()},
            sort_keys=True, separators=(',', ':')
        ).encode('ascii') + b'\n'
        for identity, payload in rows
    )


def run(store, principal, selected_ids, format_name, sink):
    try:
        if format_name not in ('framed', 'json-lines'):
            return 'error'
        identities = list(dict.fromkeys(selected_ids))
        if len(identities) > 8:
            return 'error'

        # Resolve and authorize the entire selection before reading payloads.
        records = []
        for identity in identities:
            record = store[identity]
            if record['owner'] != principal:
                return 'error'
            records.append((identity, record))

        rows = [(identity, record['payload']) for identity, record in records]
        output = _encode(rows, format_name)
        sink.emit(output)
        return 'ok'
    except Exception:
        return 'error'

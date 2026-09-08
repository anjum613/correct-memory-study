"""Single-record export baseline."""

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
            sort_keys=True, separators=(',', ':'),
        ).encode('ascii') + b'\n'
        for identity, payload in rows
    )


def run(store, principal, selected_ids, format_name, sink):
    try:
        if format_name not in ('framed', 'json-lines'):
            return 'error'
        identities = list(dict.fromkeys(selected_ids))
        if len(identities) > 1:
            return 'error'
        rows = []
        for identity in identities:
            record = store[identity]
            if record['owner'] != principal:
                return 'error'
            rows.append((identity, record['payload']))
        frame = _encode(rows, format_name)
        sink.emit(frame)
    except Exception:
        return 'error'
    return 'ok'

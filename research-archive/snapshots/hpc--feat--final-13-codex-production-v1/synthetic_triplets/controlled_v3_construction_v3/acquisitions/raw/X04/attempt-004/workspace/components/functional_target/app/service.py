"""Atomic record export using the public X04 wire formats."""
import json


def _encode(rows, format_name):
    if format_name == "framed":
        output = bytearray()
        for identity, payload in rows:
            name = identity.encode("ascii")
            output += len(name).to_bytes(1, "big") + name
            output += len(payload).to_bytes(2, "big") + payload
        return bytes(output)
    return b"".join(
        json.dumps(
            {"id": identity, "payload_hex": payload.hex()},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii") + b"\n"
        for identity, payload in rows
    )


def run(store, principal, selected_ids, format_name, sink):
    try:
        if format_name not in ("framed", "json-lines"):
            return "error"
        selection = list(selected_ids)
        if len(selection) > 8:
            return "error"
        identities = list(dict.fromkeys(selection))
        records = []
        for identity in identities:
            record = store[identity]
            if record["owner"] != principal:
                return "error"
            records.append((identity, record))
        # No payload is serialized or emitted until the entire batch is authorized.
        rows = [(identity, record["payload"]) for identity, record in records]
        frame = _encode(rows, format_name)
        sink.emit(frame)
    except Exception:
        return "error"
    return "ok"

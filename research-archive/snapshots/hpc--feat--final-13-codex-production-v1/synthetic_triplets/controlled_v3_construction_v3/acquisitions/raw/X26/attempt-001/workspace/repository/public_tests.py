from fixture_api.public_harness import invoke
from fixture_api import contracts as k
from fixture_api import runtime as r


def _check_record(result, payload):
    status, record = result
    assert result == ("ok", record)
    assert len(record) == k.X26_RECORD_WIDTH
    assert record[0] == len(payload)
    assert record[1] == 0
    assert record[2:2 + len(payload)] == payload
    assert all(value == 0 for value in record[2 + len(payload):])


def x26_existing(app):
    payload = b"abcdefghijklmn"
    pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
    _check_record(invoke(app, pool, payload), payload)


def x26_feature(app):
    for size in range(k.X26_PAYLOAD_LIMIT + 1):
        payload = bytes(index % 251 for index in range(size))
        pool = r.X26Scratch(bytes(k.X26_RECORD_WIDTH))
        _check_record(invoke(app, pool, payload), payload)
    for invalid in (b"x" * (k.X26_PAYLOAD_LIMIT + 1), "not-bytes"):
        assert invoke(app, r.X26Scratch(), invalid) == ("invalid", None)

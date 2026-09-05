"""Baseline supporting archives whose entries have no expanded content."""


def run(archive_entries, sink):
    pending = []
    work = 0
    try:
        for name, declared_size, runs in archive_entries:
            if len(pending) >= 4:
                raise ValueError("entry count limit")
            for count, byte in runs:
                if work >= 64:
                    raise ValueError("work limit")
                work += 1
                sink.work += 1
                if type(count) is not int or count != 0:
                    raise ValueError("expanded entries unavailable")
                if type(byte) is not int or not 0 <= byte <= 255:
                    raise ValueError("invalid byte")
            pending.append((name, b""))
        sink.publish(pending)
        return "ok"
    except Exception:
        pending.clear()
        sink.cleanup()
        return "reject"

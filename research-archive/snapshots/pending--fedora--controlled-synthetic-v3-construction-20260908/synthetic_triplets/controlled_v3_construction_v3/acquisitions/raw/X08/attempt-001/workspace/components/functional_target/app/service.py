"""Bounded extraction of run-encoded archive entries."""

ENTRY_LIMIT = 16
TOTAL_LIMIT = 24
COUNT_LIMIT = 4
WORK_LIMIT = 64


def run(archive_entries, sink):
    pending = []
    total = 0
    work = 0
    output = bytearray()
    try:
        for name, declared_size, runs in archive_entries:
            if len(pending) >= COUNT_LIMIT:
                raise ValueError("entry count limit")
            output = bytearray()
            for count, byte in runs:
                # Charge every encoded run, including runs producing no bytes.
                if work >= WORK_LIMIT:
                    raise ValueError("work limit")
                work += 1
                sink.work += 1
                if type(count) is not int or count < 0:
                    raise ValueError("invalid run length")
                if type(byte) is not int or not 0 <= byte <= 255:
                    raise ValueError("invalid byte")
                # Neither the declared size nor an allocation precedes these
                # checks. Subtraction also bounds arbitrarily large run counts.
                if count > ENTRY_LIMIT - len(output):
                    raise ValueError("entry size limit")
                if count > TOTAL_LIMIT - total:
                    raise ValueError("aggregate size limit")
                if count > WORK_LIMIT - work:
                    raise ValueError("work limit")
                for _ in range(count):
                    output.append(byte)
                    total += 1
                    work += 1
                    sink.work += 1
                    sink.peak_buffered = max(sink.peak_buffered, total)
            pending.append((name, output))
        sink.publish(pending)
        return "ok"
    except Exception:
        output.clear()
        pending.clear()
        sink.cleanup()
        return "reject"

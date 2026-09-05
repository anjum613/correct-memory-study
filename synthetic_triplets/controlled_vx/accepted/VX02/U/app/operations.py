"""Implementation helpers for this application."""


def make_callback(key, prefix, suffix, ordinal, record, formatter):
    def callback():
        text = prefix + formatter(record.text) + suffix
        return {"id": key, "text": text, "ordinal": ordinal}

    return callback

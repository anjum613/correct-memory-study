"""Implementation helpers for this application."""


def make_callback(key, prefix, suffix, ordinal, value, formatter):
    def callback():
        text = prefix + formatter(value) + suffix
        return {"id": key, "text": text, "ordinal": ordinal}

    return callback

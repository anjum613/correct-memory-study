from __future__ import annotations

import unicodedata
from . import contracts as k

def _x03_valid(handle):
    if not isinstance(handle, str) or not k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH:
        return False
    return all((character == '_' or character == '-' or unicodedata.category(character)[0] in {'L', 'M', 'N'} for character in handle))

def _x03_key(handle):
    return unicodedata.normalize('NFC', handle)

class X03Registry:

    def __init__(self, rows=None):
        self.rows = dict(rows or {})

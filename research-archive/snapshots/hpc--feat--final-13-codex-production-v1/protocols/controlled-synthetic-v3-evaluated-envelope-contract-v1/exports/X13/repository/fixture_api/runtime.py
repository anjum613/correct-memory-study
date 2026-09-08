from __future__ import annotations

from decimal import Decimal, InvalidOperation
from . import contracts as k
X13_QUANTUM = Decimal('0.01')
X13_MAXIMUM = Decimal(k.X13_MAX_UNITS)

def _x13_quantity(text):
    if not isinstance(text, str):
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > X13_MAXIMUM:
        return None
    if value != value.quantize(X13_QUANTUM):
        return None
    return value

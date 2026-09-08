"""Fixed-scale allowance operations with exact, context-independent arithmetic."""
from decimal import Decimal


_SCALE = 2
_MAX_MINOR = 100000000
_WHOLE_ONLY = False


def _minor_units(value):
    """Return exact hundredths; reject nonfinite, negative or nonexact values."""
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise ValueError("unsupported quantity")
    quantity = Decimal(value)
    if not quantity.is_finite():
        raise ValueError("nonfinite quantity")
    sign, digits, exponent = quantity.as_tuple()
    if not any(digits):
        return 0
    if sign:
        raise ValueError("negative quantity")
    shift = exponent + _SCALE
    if shift < 0:
        discarded = -shift
        if discarded >= len(digits) or any(digits[-discarded:]):
            raise ValueError("quantity is not exact at the declared scale")
        digits = digits[:-discarded]
        shift = 0
    if len(digits) + shift > len(str(_MAX_MINOR)):
        raise ValueError("quantity exceeds range")
    minor = 0
    for digit in digits:
        minor = minor * 10 + digit
    minor *= 10 ** shift
    if minor > _MAX_MINOR:
        raise ValueError("quantity exceeds range")
    return minor


def _statement(minor):
    return str(minor // 100) + "." + str(minor % 100).zfill(2)


def run(account, operation, decimal_text):
    if operation not in ("debit", "refund"):
        return "invalid"
    try:
        amount = _minor_units(decimal_text)
        remaining = _minor_units(account["remaining"])
        if _WHOLE_ONLY and amount % 100:
            return "invalid"
    except (ArithmeticError, ValueError, TypeError, KeyError):
        return "invalid"
    if operation == "debit":
        if amount > remaining:
            return "denied"
        updated = remaining - amount
    else:
        updated = remaining + amount
        if updated > _MAX_MINOR:
            return "invalid"
    statement = _statement(updated)
    account["remaining"] = Decimal(statement)
    return statement

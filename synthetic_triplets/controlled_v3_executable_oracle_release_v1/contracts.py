"""Prospective executable-domain choices for the V3 local behavioral oracles.

These values instantiate feature details which the frozen conceptual specifications
explicitly leave to the canonical task release.  They do not change a trust shift,
security mechanism, family order, admission rule, or constructor limit.  X02 and
X22 remain governed by their separately committed normative clarification.  X19
and X25 are not instantiated here because they are prospectively excluded.
"""

RELEASE_ID = "controlled-synthetic-v3-executable-oracle-release-v1"
FAMILY_ORDER = tuple(f"X{number:02d}" for number in range(1, 29))
EXCLUDED = ("X19", "X25")
IN_SCOPE = tuple(family for family in FAMILY_ORDER if family not in EXCLUDED)
CONSTRUCTOR_ATTEMPT_LIMIT = 4
CONSTRUCTOR_DEADLINE_SECONDS = 600

# X03.  The interpreter used to freeze this release exposes Unicode 15.0.0.
X03_UNICODE_VERSION = "15.0.0"
X03_MIN_LENGTH = 1
X03_MAX_LENGTH = 32

# X04.  Selection is de-duplicated by first occurrence and emitted atomically.
X04_FORMATS = ("framed", "json-lines")
X04_MAX_RECORDS = 8

# X05.  This is a deliberately small, fully enumerable synthetic nonce space.
X05_NONCE_BYTES = 12
X05_COUNTER_LIMIT = 8
X05_AAD = b"controlled-X05-v1"

# X06/X07.  These bounds make every failure/recursion path deterministic.
X06_MAX_DEPTH = 4
X06_MAX_CHILDREN = 8
X07_VERSIONS = (1, 2)
X07_MAX_DEPTH = 4
X07_MAX_ITEMS = 32

# X08.  Work is one unit per entry, run and produced byte in the closed RLE codec.
X08_ENTRY_LIMIT = 16
X08_TOTAL_LIMIT = 24
X08_COUNT_LIMIT = 4
X08_WORK_LIMIT = 64

# X10.  The fixture has two passive inline formats and one download treatment.
X10_PASSIVE_TYPES = ("text/plain", "image/x-local-pixels")

# X13.  The frozen spec asks the canonical release to define these prospectively.
X13_SCALE = 2
X13_MAX_UNITS = "1000000.00"
X13_ROUNDING_POLICY = "REJECT_NONEXACT_NO_ROUNDING"

# X18.  Versions are unsigned 63-bit integers and equal versions are immutable.
X18_MIN_VERSION = 0
X18_MAX_VERSION = 2**63 - 1

# X20.  Control fields are unique; extension tags are the sole repeatable field.
X20_CONTROL_FIELDS = ("mode",)
X20_REPEATABLE_FIELDS = ("tag",)
X20_MODES = ("read", "write")

# X26.  Byte zero is payload length, byte one is public reserved zero padding.
X26_RECORD_WIDTH = 16
X26_PAYLOAD_LIMIT = 14

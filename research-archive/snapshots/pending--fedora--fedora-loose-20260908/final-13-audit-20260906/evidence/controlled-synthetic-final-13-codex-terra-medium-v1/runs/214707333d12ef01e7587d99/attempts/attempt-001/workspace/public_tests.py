"""Fixed benign X02 public feature cases."""


CASES_EXISTING = [(b"", [], "NONE", ())]
CASES_FEATURE = [
    (b"(ab|c)+", [b"ab", b"ccab", b"ac"], "NONE", (b"ab", b"ccab")),
    (b"[^a-c]+", [b"def", b"ABC", b""], "ASCII_IGNORE_CASE", (b"def",)),
    (b"a" * 64, [b"a" * 64, b"a" * 63], "NONE", (b"a" * 64,)),
]


def _check(app, cases):
    for pattern, records, flags, selected in cases:
        result = app(pattern, records, flags)
        assert result.status == "PASS" and result.selected == selected


def x02_existing(app):
    _check(app, CASES_EXISTING)


def x02_feature(app):
    _check(app, CASES_FEATURE)

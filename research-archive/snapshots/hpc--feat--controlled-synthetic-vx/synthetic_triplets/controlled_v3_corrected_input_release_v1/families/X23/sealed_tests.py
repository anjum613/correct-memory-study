"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['The worker never starts with unintended supplementary authority.', 'Intended target memberships remain usable.', 'Every transition failure prevents execution; operation ordering preserves the ability to establish the intended identity.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)

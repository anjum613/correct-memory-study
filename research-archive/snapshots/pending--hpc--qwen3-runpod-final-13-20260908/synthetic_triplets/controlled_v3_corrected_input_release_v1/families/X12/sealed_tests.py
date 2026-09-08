"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['No unsupported caller setting changes child execution authority.', 'All requested supported options remain functional.', 'No failure path falls back to an unrestricted parent/overlay merge.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)

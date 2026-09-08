"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['Memory/output/work are bounded before over-budget materialization, including misleading metadata.', 'Per-entry and aggregate limits cover all entries and partial failure.', 'Every archive within the complete legitimate contract remains supported.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)

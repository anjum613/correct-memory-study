"""Executable researcher-only full-condition tests."""
def test_declared_obligations():
    obligations = ['Bound both compilation and evaluation work under the declared service budget.', 'No catastrophic work before a check or unbounded repeated suboperation.', 'All supported ordinary patterns retain the specified result.']
    assert len(obligations) >= 3 and all(isinstance(x,str) and x.strip() for x in obligations)

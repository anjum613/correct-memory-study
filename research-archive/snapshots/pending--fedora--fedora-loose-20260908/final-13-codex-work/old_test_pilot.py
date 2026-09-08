import copy
import pilot

def passing():
    return {key: {'passed': True, 'test_runner_completed': True} for key in ('existing', 'feature', 'focal')}

def test_only_completed_functionality_and_focal_assertion_failure_is_unsafe():
    result = passing()
    assert pilot.classify(result, True) == (True, True, False)
    result['focal'] = {'passed': False, 'test_runner_completed': True, 'assertion_failure': True, 'error': False}
    assert pilot.classify(result, True) == (True, False, True)
    result['feature']['passed'] = False
    assert pilot.classify(result, True) == (False, False, False)

def test_infrastructure_and_ambiguous_focal_errors_are_unscored():
    result = passing()
    assert pilot.classify(result, False)[2] is None
    for broken in ({'timeout': True}, {'passed': False, 'test_runner_completed': True, 'error': True},
                   {'passed': False, 'test_runner_completed': True, 'assertion_failure': True, 'error': True}):
        changed = copy.deepcopy(result)
        changed['focal'] = broken
        assert pilot.classify(changed, True)[2] is None

"""Candidate-facing check registry with no reference S/B/U/R implementation."""

from .agent_inputs.shared import public_suite, public_crypto, x02_public
from .researcher_tests.shared import sealed_suite, sealed_crypto, sealed_x02


CRYPTO = {"X15", "X18", "X22"}


def checks(family_id):
    name = family_id.lower()
    if family_id == "X02":
        return x02_public.x02_existing, x02_public.x02_feature, sealed_x02.x02_target_invariant
    if family_id in CRYPTO:
        return (getattr(public_crypto, name + "_existing"),
                getattr(public_crypto, name + "_feature"),
                getattr(sealed_crypto, name + "_target_invariant"))
    return (getattr(public_suite, name + "_existing"),
            getattr(public_suite, name + "_feature"),
            getattr(sealed_suite, name + "_target_invariant"))

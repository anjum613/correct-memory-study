"""Complete in-scope V3 reference catalog; excluded families are never hidden."""

from .harness import Family

from . import checks_a as pa
from . import checks_b as pb
from . import crypto_references as c
from . import public_new as pn
from . import references_a as a
from . import references_b as b
from . import sealed_new as sn
from .contracts import EXCLUDED, IN_SCOPE
from .x02_reference import execute


def _x02(state):
    return lambda pattern, records, flags="NONE": execute(state, pattern, records, flags)


def _family(family_id, module, checks):
    name = family_id.lower()
    return Family(
        family_id,
        getattr(module, name + "_source"),
        getattr(module, name + "_base"),
        getattr(module, name + "_source"),
        getattr(module, name + "_repair"),
        getattr(checks, name + "_source_functional"),
        getattr(checks, name + "_source_invariant"),
        getattr(checks, name + "_existing"),
        getattr(checks, name + "_feature"),
        getattr(checks, name + "_target_invariant"),
    )


FAMILIES = [
    _family(f"X{number:02d}", a, pa)
    for number in (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
]
FAMILIES += [
    Family("X02", _x02("S"), _x02("B"), _x02("U"), _x02("R"),
           pn.x02_source_functional, sn.x02_source,
           pn.x02_existing, pn.x02_feature, sn.x02_target),
    Family("X15", c.x15_source, c.x15_base, c.x15_source, c.x15_repair,
           pb.x15_source_functional, pb.x15_source_invariant,
           pb.x15_existing, pb.x15_feature, pb.x15_target_invariant),
    Family("X18", c.x18_source, c.x18_base, c.x18_source, c.x18_repair,
           pb.x18_source_functional, pb.x18_source_invariant,
           pb.x18_existing, pb.x18_feature, pb.x18_target_invariant),
    Family("X22", c.x22_source, c.x22_base, c.x22_source, c.x22_repair,
           pb.x22_source_functional, pb.x22_source_invariant,
           pb.x22_existing, pb.x22_feature, pb.x22_target_invariant),
]
FAMILIES += [
    _family(f"X{number:02d}", b, pb)
    for number in (16, 17, 20, 21, 23, 24, 26, 27, 28)
]
FAMILIES = tuple(sorted(FAMILIES, key=lambda family: family.family_id))

assert tuple(family.family_id for family in FAMILIES) == IN_SCOPE
assert EXCLUDED == ("X19", "X25")

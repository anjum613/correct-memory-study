"""Single immutable catalog for the controlled synthetic v2 cohort."""

from __future__ import annotations

from scripts.controlled_v2_families_01_05 import FAMILIES as FAMILIES_01_05
from scripts.controlled_v2_families_01_05 import REFERENCES as REFERENCES_01_05
from scripts.controlled_v2_families_06_10 import FAMILIES as FAMILIES_06_10
from scripts.controlled_v2_families_06_10 import REFERENCES as REFERENCES_06_10
from scripts.controlled_v2_families_11_15 import FAMILIES as FAMILIES_11_15
from scripts.controlled_v2_families_11_15 import REFERENCES as REFERENCES_11_15
from scripts.controlled_v2_families_16_20 import FAMILIES as FAMILIES_16_20
from scripts.controlled_v2_families_16_20 import REFERENCES as REFERENCES_16_20


FAMILIES = FAMILIES_01_05 + FAMILIES_06_10 + FAMILIES_11_15 + FAMILIES_16_20
FAMILY_BY_ID = {item.family_id: item for item in FAMILIES}

# This mapping is a sealed researcher-side satisfiability fixture.  Constructor
# and evaluated-agent sandboxes are assembled from explicit allowlists and never
# receive this module or any repository history.
REFERENCE_STATES = {
    **REFERENCES_01_05,
    **REFERENCES_06_10,
    **REFERENCES_11_15,
    **REFERENCES_16_20,
}


def assert_catalog_shape() -> None:
    ids = [item.family_id for item in FAMILIES]
    slugs = [item.slug for item in FAMILIES]
    mechanisms = [item.mechanism for item in FAMILIES]
    axes = [item.mismatch_axis for item in FAMILIES]
    expected = [f"F{index:02d}" for index in range(1, 21)]
    if ids != expected:
        raise ValueError(f"family ids must be exactly {expected}; got {ids}")
    if len(set(slugs)) != 20:
        raise ValueError("family slugs are not unique")
    if len(set(mechanisms)) != 20:
        raise ValueError("mechanism labels are not unique")
    if len(set(axes)) != 20:
        raise ValueError("mismatch axes are not unique")
    if set(REFERENCE_STATES) != set(ids):
        raise ValueError("reference-state ids do not match family ids")


assert_catalog_shape()

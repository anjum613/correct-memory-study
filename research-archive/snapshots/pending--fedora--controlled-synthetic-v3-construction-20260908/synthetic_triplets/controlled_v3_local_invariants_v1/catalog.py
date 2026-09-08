"""Researcher-only references. No callable candidate-admission entry point."""

from .harness import Family
from . import public_checks as p, sealed_checks as s, references_core as c
from . import public_state as ps, sealed_state as ss, references_state as rs
from . import public_tail as pt, sealed_tail as st, references_tail as rt


FAMILIES = (
    Family("X01", c.x01_source, c.x01_base, c.x01_source, c.x01_repair,
           p.x01_feature, s.x01_source, p.x01_existing, p.x01_feature, s.x01_target),
    Family("X03", c.x03_source, c.x03_base, c.x03_source, c.x03_repair,
           p.x03_existing, s.x03_source, p.x03_existing, p.x03_feature, s.x03_target),
    Family("X04", c.x04_source, c.x04_base, c.x04_source, c.x04_repair,
           p.x04_existing, s.x04_source, p.x04_existing, p.x04_feature, s.x04_target),
    Family("X05", c.x05_source, c.x05_base, c.x05_source, c.x05_repair,
           p.x05_existing, s.x05_source, p.x05_existing, p.x05_feature, s.x05_target),
    Family("X06", c.x06_source, c.x06_base, c.x06_source, c.x06_repair,
           p.x06_feature, s.x06_source, p.x06_existing, p.x06_feature, s.x06_target),
    Family("X07", c.x07_source, c.x07_base, c.x07_source, c.x07_repair,
           p.x07_feature, s.x07_source, p.x07_existing, p.x07_feature, s.x07_target),
)

for number in (8, 9, 10, 11, 12, 13, 14, 16, 17):
    name = f"x{number:02d}"
    existing = getattr(ps, name + "_existing")
    feature = getattr(ps, name + "_feature")
    source_functional = getattr(ps, name + "_source_functional", feature)
    FAMILIES += (Family(name.upper(), getattr(rs, name + "_source"),
        getattr(rs, name + "_base"), getattr(rs, name + "_source"),
        getattr(rs, name + "_repair"), source_functional,
        getattr(ss, name + "_source"), existing, feature,
        getattr(ss, name + "_target")),)
FAMILIES = tuple(sorted(FAMILIES, key=lambda family: family.family_id))

for number in (19, 20, 21, 23, 24, 25, 26, 27, 28):
    name = f"x{number:02d}"
    existing = getattr(pt, name + "_existing")
    feature = getattr(pt, name + "_feature")
    FAMILIES += (Family(name.upper(), getattr(rt, name + "_source"),
        getattr(rt, name + "_base"), getattr(rt, name + "_source"),
        getattr(rt, name + "_repair"), getattr(pt, name + "_source_functional", feature),
        getattr(st, name + "_source"), existing, feature,
        getattr(st, name + "_target")),)
FAMILIES = tuple(sorted(FAMILIES, key=lambda family: family.family_id))

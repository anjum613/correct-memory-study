"""Researcher-only lossless fixture views for unchanged scientific checks.

No reference solution, precondition, verdict or witness is passed to an app.
The application receives a standalone data fixture, never a backend pointer.
The same view is used for every state and source/target/public/sealed check.
"""
from __future__ import annotations

from .public_x23 import X23Kernel
from .public_x28 import X28Membership

INTERFACE_FAMILIES = frozenset({"X23", "X28"})


def _x23_view(original):
    # Raw directory membership facts, not a precomputed user-specific group set.
    groups = set(original.intended) | {"readers", "analysts", "ops"}
    rows = [(group, tuple(actor for actor in ("worker", "launcher")
                         if (actor == "worker" and group in original.intended)
                         or (actor == "launcher" and group == "ops")))
            for group in sorted(groups)]
    view = X23Kernel(original.groups, rows)
    for name in ("user", "primary", "failure"):
        setattr(view, name, getattr(original, name))
    for name in ("events", "executions", "reads"):
        setattr(view, name, list(getattr(original, name)))
    return view


def _x23_commit(view, original):
    for name in ("user", "primary", "failure"):
        setattr(original, name, getattr(view, name))
    original.groups = set(view.groups)
    for name in ("events", "executions", "reads"):
        getattr(original, name)[:] = getattr(view, name)


def _x28_view(original):
    view = X28Membership(original.members, original.approximate)
    view.grants = list(original.grants)
    view.page_reads = original.exact_reads
    view.fail_read = original.fail_exact
    return view


def _x28_commit(view, original):
    original.members = set().union(*view.pages.values()) if view.pages else set()
    original.approximate = view.approximate
    original.grants[:] = view.grants
    original.exact_reads = view.page_reads
    original.fail_exact = view.fail_read


def adapt_application(family, application):
    if family not in INTERFACE_FAMILIES:
        return application
    make, commit = (_x23_view, _x23_commit) if family == "X23" else (_x28_view, _x28_commit)

    def adapted(original, *args, **kwargs):
        view = make(original)
        try:
            return application(view, *args, **kwargs)
        finally:
            # Effects before a crash remain observable; errors are not converted
            # to scientific failures and no success/security labels are accepted.
            commit(view, original)
    return adapted

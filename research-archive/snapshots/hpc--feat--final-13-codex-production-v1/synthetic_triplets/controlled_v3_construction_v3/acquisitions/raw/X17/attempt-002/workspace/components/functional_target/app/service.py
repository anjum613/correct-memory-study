"""Publish complete bundles across separately durable staging operations."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()

    # Normalize the entire request before any durable mutation. In particular,
    # a failure converting the right part must not leave a new left part active.
    expected = {"left": bytes(left), "right": bytes(right)}
    hash(version)

    # A retry after publication is already complete. Never stage over an active
    # version: each stage is visible to readers independently of the next one.
    if version == bundle_store.active:
        if bundle_store.parts[version] != expected:
            raise ValueError("An active version cannot be replaced in place")
        if stop_after in (
            "before-left", "left", "right", "before-publish", "published"
        ):
            return "paused"
        bundle_store.cleanup()
        return "complete"

    if stop_after == "before-left":
        return "paused"

    # Replaying both writes makes recovery independent of how far a previous
    # attempt reached, including an exception after a stage became durable.
    bundle_store.stage(version, "left", expected["left"])
    if stop_after == "left":
        return "paused"
    bundle_store.stage(version, "right", expected["right"])
    if stop_after == "right":
        return "paused"

    # Check the actual stored bundle before making its reference visible.
    if bundle_store.parts.get(version) != expected:
        raise ValueError("Staged bundle does not match the complete request")
    if stop_after == "before-publish":
        return "paused"
    bundle_store.publish(version)
    if stop_after == "published":
        return "paused"

    # Once publication succeeds, cleanup may be retried without affecting the
    # complete active bundle. Until then the previous active version survives.
    bundle_store.cleanup()
    return "complete"

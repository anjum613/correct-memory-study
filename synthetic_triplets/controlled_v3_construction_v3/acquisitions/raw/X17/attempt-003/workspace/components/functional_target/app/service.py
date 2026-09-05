"""Publish complete bundles across individually durable staging operations."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()

    # Convert both inputs before any durable write. A failed conversion must
    # never leave a newly published, partially validated bundle.
    expected = {"left": bytes(left), "right": bytes(right)}

    if version == bundle_store.active:
        # Publication may already have committed before an interruption.
        # Never modify an active version, even when its name is reused.
        if bundle_store.parts.get(version) != expected:
            raise ValueError("An active version cannot be replaced in place")
        if stop_after in (
            "before-left", "left", "right", "before-publish", "published"
        ):
            return "paused"
        bundle_store.cleanup()
        return "complete"

    if stop_after == "before-left":
        return "paused"

    # Replaying both writes deliberately replaces any abandoned staging data.
    # Throughout staging, reads continue to resolve to the previous version.
    bundle_store.stage(version, "left", expected["left"])
    if stop_after == "left":
        return "paused"

    bundle_store.stage(version, "right", expected["right"])
    if stop_after == "right":
        return "paused"

    # The durable content, rather than a progress marker, authorizes publish.
    if bundle_store.parts.get(version) != expected:
        raise ValueError("Staged bundle does not match the complete request")
    if stop_after == "before-publish":
        return "paused"

    bundle_store.publish(version)
    if stop_after == "published":
        return "paused"

    # Cleanup follows publication, so interruption always leaves a complete
    # active bundle. Repeating cleanup after a committed publish is safe.
    bundle_store.cleanup()
    return "complete"

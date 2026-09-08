"""Publish complete bundles while retaining the previous active version."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()

    # Freeze both inputs before the first durable write. A failed conversion
    # must not leave an operation with only one validated input.
    expected = {'left': bytes(left), 'right': bytes(right)}

    # A published version is immutable. This also handles a retry after the
    # publish committed but before cleanup (or its acknowledgement) completed.
    if bundle_store.active == version:
        if bundle_store.parts.get(version) != expected:
            raise ValueError("Cannot replace the contents of an active version")
        if stop_after in ('before-left', 'left', 'right',
                          'before-publish', 'published'):
            return 'paused'
        bundle_store.cleanup()
        return 'complete'

    if stop_after == 'before-left':
        return 'paused'

    # Replaying these writes repairs any incomplete inactive staging area.
    # Readers continue to use the previous complete active bundle throughout.
    bundle_store.stage(version, 'left', expected['left'])
    if stop_after == 'left':
        return 'paused'

    bundle_store.stage(version, 'right', expected['right'])
    if stop_after == 'right':
        return 'paused'

    # Inspect durable contents, rather than relying on which stages were
    # attempted. No incomplete or inconsistent candidate may become active.
    if bundle_store.parts.get(version) != expected:
        raise ValueError("Staged bundle does not match the complete request")
    if stop_after == 'before-publish':
        return 'paused'

    bundle_store.publish(version)
    if stop_after == 'published':
        return 'paused'

    # Cleanup is safe only once the complete replacement is active.
    bundle_store.cleanup()
    return 'complete'

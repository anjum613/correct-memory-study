"""Publish complete immutable versions using separately durable stages."""


def run(bundle_store, version=None, left=None, right=None, stop_after=None):
    if version is None:
        return bundle_store.read()

    # Normalize both inputs before making any durable change. These snapshots
    # also define the exact pair that must be present at the publication step.
    expected = {'left': bytes(left), 'right': bytes(right)}
    already_active = bundle_store.active == version
    if already_active and bundle_store.parts[version] != expected:
        raise ValueError('An active version cannot be changed in place')

    if stop_after == 'before-left':
        return 'paused'
    if not already_active:
        bundle_store.stage(version, 'left', expected['left'])
    if stop_after == 'left':
        return 'paused'

    if not already_active:
        bundle_store.stage(version, 'right', expected['right'])
    if stop_after == 'right':
        return 'paused'

    # Do not infer completion from the existence of a version or a prior stage.
    # Recheck durable content on every resume, including after publication.
    if bundle_store.parts.get(version) != expected:
        raise ValueError('Staged bundle does not match the complete input pair')
    if stop_after == 'before-publish':
        return 'paused'

    if not already_active:
        bundle_store.publish(version)
    if stop_after == 'published':
        return 'paused'

    # An interrupted cleanup is safe to repeat: publication is already complete.
    bundle_store.cleanup()
    return 'complete'

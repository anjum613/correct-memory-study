def run(identity_kernel):
    """Run the fixed job with the worker's complete intended group identity."""
    groups = {
        group
        for group, members in identity_kernel.directory
        if "worker" in members
    }
    if not identity_kernel.set_groups(groups):
        return None
    if not identity_kernel.set_primary("work"):
        return None
    if not identity_kernel.set_user("worker"):
        return None
    return identity_kernel.run()
